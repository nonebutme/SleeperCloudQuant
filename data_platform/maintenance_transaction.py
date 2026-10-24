"""数据维护事务：只缓存下载增量；未通过检查的业务写入不对外可见。"""
from __future__ import annotations

from contextlib import closing, contextmanager
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
import sqlite3
import threading

_active = ContextVar("maintenance_transaction", default=None)
_readers_lock = threading.RLock()
_readers = {}


class TransactionConnection:
    """让现有 store 的短连接参与同一外层事务，禁止内部提前提交。"""

    def __init__(self, connection):
        self.connection = connection
        self.savepoint = None

    def execute(self, sql, parameters=()):
        normalized = sql.strip().rstrip(";").strip().upper()
        if normalized.startswith(("PRAGMA JOURNAL_MODE", "PRAGMA SYNCHRONOUS", "PRAGMA QUERY_ONLY")):
            return self.connection.execute("SELECT 1")
        if normalized in {"BEGIN", "BEGIN IMMEDIATE", "BEGIN EXCLUSIVE", "COMMIT"}:
            return self.connection.execute("SELECT 1")
        return self.connection.execute(sql, parameters)

    def executemany(self, sql, parameters):
        return self.connection.executemany(sql, parameters)

    def executescript(self, script):
        statement = ""
        for character in script:
            statement += character
            if character == ";" and sqlite3.complete_statement(statement):
                self.execute(statement)
                statement = ""
        if statement.strip():
            self.execute(statement)

    def __enter__(self):
        import uuid
        self.savepoint = "store_" + uuid.uuid4().hex
        self.connection.execute(f"SAVEPOINT {self.savepoint}")
        return self

    def __exit__(self, kind, value, traceback):
        if kind:
            self.connection.execute(f"ROLLBACK TO {self.savepoint}")
        self.connection.execute(f"RELEASE {self.savepoint}")

    def close(self):
        pass

    def commit(self):
        pass

    def rollback(self):
        _active.get()[2]['rollback_only'] = True


def transaction_connection(path):
    active = _active.get()
    if active is not None and Path(path).resolve() == active[0]:
        return TransactionConnection(active[1])
    return None


def record_activation(connection, batch_id, version_id):
    connection.execute("CREATE TABLE IF NOT EXISTS maintenance_commits "
                       "(batch_id TEXT PRIMARY KEY, data_version_id TEXT NOT NULL)")
    connection.execute("INSERT OR IGNORE INTO maintenance_commits VALUES (?,?)", (batch_id, version_id))


def materialize_price_corrections(connection, version_id=None, *, selected_issue_ids=None, selected_price_keys=None):
    """将已生效且可追溯的价格修正纳入规范事实，防止后续重拉覆盖。"""
    import json
    if version_id is None:
        row = connection.execute("SELECT setting_value FROM data_center_settings WHERE setting_key='default_data_version_id'").fetchone()
        version_id = row[0] if row else None
    if not version_id:
        return
    rows = connection.execute("""
        WITH RECURSIVE ancestry(data_version_id, parent_version_id) AS (
            SELECT data_version_id, parent_version_id FROM data_versions WHERE data_version_id=?
            UNION
            SELECT v.data_version_id, v.parent_version_id FROM data_versions v
            JOIN ancestry a ON v.data_version_id=a.parent_version_id
        )
        SELECT o.issue_id,o.symbol,o.observation_at,o.after_json,i.evidence_json
        FROM data_correction_overlays o JOIN data_quality_issues i ON i.issue_id=o.issue_id
        WHERE o.dataset='a_share_daily' AND o.status='published'
          AND o.data_version_id IN (SELECT data_version_id FROM ancestry)
        ORDER BY o.created_at,o.overlay_id
    """, (version_id,)).fetchall()
    fields = {'open','high','low','close','volume','amount','amplitude','change_pct','change_amount','turnover_rate'}
    for row in rows:
        if selected_issue_ids is not None and row['issue_id'] not in selected_issue_ids:
            continue
        changes = {key: value for key, value in json.loads(row['after_json']).items() if key in fields}
        adjustment = str(json.loads(row['evidence_json']).get('adjustment') or '')
        if selected_price_keys is not None and (row['symbol'], str(row['observation_at'])[:10], adjustment) not in selected_price_keys:
            continue
        if not changes or adjustment not in {'raw','qfq','hfq'}:
            raise ValueError('价格修正缺少字段或明确复权口径，不能自动生效')
        connection.execute(
            'UPDATE market_daily_prices SET ' + ','.join(f'{key}=?' for key in changes)
            + ' WHERE symbol=? AND trade_date=? AND adjustment=?',
            (*changes.values(), row['symbol'], str(row['observation_at'])[:10], adjustment),
        )


def _guard_path(path):
    return Path(str(Path(path).resolve()) + ".research-lock.sqlite3")


def ensure_research_guard(path):
    guard = _guard_path(path)
    if guard.exists():
        with closing(sqlite3.connect(guard)) as connection:
            if connection.execute("SELECT id FROM guard WHERE id=1").fetchone():
                return
    with closing(sqlite3.connect(guard)) as connection, connection:
        connection.execute("CREATE TABLE IF NOT EXISTS guard (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT OR IGNORE INTO guard VALUES (1)")


@contextmanager
def stable_research_read(path):
    """跨线程/跨进程共享读锁；更新提交须取得排他锁。"""
    guard = _guard_path(path)
    if not guard.exists():
        yield
        return
    key = str(guard)
    with _readers_lock:
        if key not in _readers:
            connection = sqlite3.connect(guard, timeout=30, check_same_thread=False)
            try:
                connection.execute("BEGIN")
                connection.execute("SELECT id FROM guard").fetchone()
            except BaseException:
                connection.close()
                raise
            _readers[key] = [connection, 0]
        _readers[key][1] += 1
    try:
        yield
    finally:
        with _readers_lock:
            entry = _readers[key]
            entry[1] -= 1
            if not entry[1]:
                entry[0].rollback()
                entry[0].close()
                del _readers[key]


def guarded_research(method):
    @wraps(method)
    def run(self, *args, **kwargs):
        path = getattr(self, "_maintenance_database_path", None)
        if path is None:
            return method(self, *args, **kwargs)
        with stable_research_read(path):
            return method(self, *args, **kwargs)
    return run


def require_current_input(owner, task):
    """没有冻结物理输入的旧任务不可冒充使用历史版本重新计算。"""
    path = getattr(owner, "_maintenance_database_path", None)
    if path is None:
        return
    with closing(sqlite3.connect(f"file:{Path(path).resolve().as_posix()}?mode=ro", uri=True)) as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='maintenance_commits'").fetchone():
            return
        current = c.execute("SELECT setting_value FROM data_center_settings WHERE setting_key='default_data_version_id'").fetchone()
    if current is None:
        raise ValueError("当前没有可用数据")
    versions = set()
    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {'data_version_id', 'data_version'} and isinstance(item, str) and item.startswith('scq-'):
                    versions.add(item)
                elif isinstance(item, (dict, list)):
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(task)
    if versions != {str(current[0])}:
        raise ValueError("historical_input_not_retained: 数据已更新或任务未绑定输入，请新建研究任务")


@contextmanager
def maintenance_transaction(path):
    if _active.get() is not None:
        raise RuntimeError("nested maintenance transaction is not supported")
    path = Path(path).resolve()
    ensure_research_guard(path)
    connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        connection.execute("BEGIN IMMEDIATE")
    except BaseException:
        connection.close()
        raise
    state = {'rollback_only': False}
    token = _active.set((path, connection, state))
    try:
        yield connection
        if state['rollback_only']:
            raise RuntimeError('inner operation requested rollback; maintenance cannot activate')
        guard = sqlite3.connect(_guard_path(path), timeout=30)
        try:
            guard.execute("BEGIN EXCLUSIVE")
            connection.commit()
        finally:
            guard.rollback()
            guard.close()
    except BaseException:
        connection.rollback()
        raise
    finally:
        _active.reset(token)
        connection.close()
