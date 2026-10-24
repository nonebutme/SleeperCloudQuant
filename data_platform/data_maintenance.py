"""一次更新：下载缓存、质量门禁、原子生效和可恢复的任务记录。"""
from __future__ import annotations

from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import json
import sqlite3
import threading
import uuid
from zoneinfo import ZoneInfo

from data_platform.a_share_sync_scheduler import AShareSyncScheduler
from data_platform.maintenance_transaction import maintenance_transaction
from data_platform.storage.data_center_store import DataCenterStore


def _dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _now():
    return datetime.now(timezone.utc).isoformat()


class _RecordingStore:
    def __init__(self, store):
        self.store = store
        self.writes = []

    def __getattr__(self, name):
        return getattr(self.store, name)

    def upsert_daily_prices(self, rows, **kwargs):
        rows = list(rows)
        self.writes.append({"rows": rows, "kwargs": kwargs})
        return self.store.upsert_daily_prices(rows, **kwargs)


class DownloadCache:
    """只缓存本次成功下载，失败响应不缓存；重试仍完整执行质量检查。"""
    def __init__(self, provider, manager, batch_id):
        self.provider = provider
        self.manager = manager
        self.batch_id = batch_id

    def __setattr__(self, name, value):
        if name == "request_gate":
            setattr(self.provider, name, value)
        else:
            object.__setattr__(self, name, value)

    def __getattr__(self, name):
        member = getattr(self.provider, name)
        if not callable(member) or not (name.startswith("fetch_") or name == "list_symbols"):
            return member
        def fetch(*args, **kwargs):
            key = _dump([name, args, kwargs])
            cached = self.manager.cached(self.batch_id, key)
            if cached is not None:
                return cached
            value = member(*args, **kwargs)
            if not isinstance(value, (list, dict, str, int, float, bool, type(None))):
                value = list(value)
            if value:
                self.manager.cache(self.batch_id, key, value)
            return value
        return fetch

    def sync_symbol(self, store, **kwargs):
        key = _dump(["sync_symbol", kwargs])
        cached = self.manager.cached(self.batch_id, key)
        if cached is not None:
            for item in cached["writes"]:
                store.upsert_daily_prices(item["rows"], **item["kwargs"])
            return cached["result"]
        recorder = _RecordingStore(store)
        result = dict(self.provider.sync_symbol(recorder, **kwargs))
        if result.get("status") == "completed" and result.get("rows_received", 0) > 0:
            self.manager.cache(self.batch_id, key, {"writes": recorder.writes, "result": result})
        return result


class DataMaintenance:
    _threads = {}
    _lock = threading.Lock()

    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.database_path = Path(scheduler.database_path).resolve()
        self.state_path = Path(str(self.database_path) + ".maintenance.sqlite3")
        self.worker_path = Path(str(self.database_path) + ".maintenance-worker.sqlite3")

    def ensure_schema(self):
        with closing(self._connect()) as c, c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS batches (
                    batch_id TEXT PRIMARY KEY, request_json TEXT NOT NULL,
                    status TEXT NOT NULL, phase TEXT NOT NULL, result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS downloads (
                    batch_id TEXT NOT NULL, request_key TEXT NOT NULL,
                    payload TEXT NOT NULL, content_hash TEXT NOT NULL,
                    PRIMARY KEY(batch_id, request_key)
                );
            """)
            expired = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            c.execute("DELETE FROM downloads WHERE batch_id IN "
                      "(SELECT batch_id FROM batches WHERE status IN ('failed','interrupted') AND updated_at<?)", (expired,))
            c.execute("UPDATE batches SET status='expired',phase='needs_attention',result_json=? "
                      "WHERE status IN ('failed','interrupted') AND updated_at<?",
                      (_dump({'error': '下载缓存已超过 7 天，请新建更新任务；更新记录保留'}), expired))
        if not self.worker_path.exists():
            with closing(sqlite3.connect(self.worker_path)) as c, c:
                c.execute("CREATE TABLE IF NOT EXISTS worker (id INTEGER PRIMARY KEY)")
                c.execute("INSERT OR IGNORE INTO worker VALUES (1)")

    def _connect(self):
        c = sqlite3.connect(self.state_path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def create(self, *, target_trade_date, effective_config=None):
        target = date.fromisoformat(str(target_trade_date)).isoformat()
        local_now = datetime.now(ZoneInfo('Asia/Shanghai'))
        latest = local_now.date() if local_now.hour >= 18 else local_now.date() - timedelta(days=1)
        if target > latest.isoformat():
            raise ValueError("请选择已收盘日期（北京时间 18:00 后可更新当日）；系统按交易日历确定截止日")
        self.ensure_schema()
        request = {"target_trade_date": target, "effective_config": dict(effective_config or {})}
        batch_id = "maintenance-" + uuid.uuid4().hex
        with closing(self._connect()) as c, c:
            c.execute("BEGIN IMMEDIATE")
            existing = c.execute(
                "SELECT batch_id FROM batches WHERE status IN ('queued','running') LIMIT 1"
            ).fetchone()
            if existing:
                raise ValueError("已有更新任务，请等待完成或恢复中断任务")
            c.execute("INSERT INTO batches VALUES (?,?,'queued','queued','{}',?,?)",
                      (batch_id, _dump(request), _now(), _now()))
        return self.get(batch_id)

    def cached(self, batch_id, key):
        with closing(self._connect()) as c:
            row = c.execute("SELECT payload,content_hash FROM downloads WHERE batch_id=? AND request_key=?",
                            (batch_id, key)).fetchone()
        if row is None:
            return None
        if sha256(row["payload"].encode()).hexdigest() != row["content_hash"]:
            raise ValueError("下载缓存校验失败，请创建新任务")
        return json.loads(row["payload"])

    def cache(self, batch_id, key, payload):
        value = _dump(payload)
        with closing(self._connect()) as c, c:
            c.execute("INSERT OR REPLACE INTO downloads VALUES (?,?,?,?)",
                      (batch_id, key, value, sha256(value.encode()).hexdigest()))

    def update(self, batch_id, status, phase, result=None):
        with closing(self._connect()) as c, c:
            c.execute("UPDATE batches SET status=?,phase=?,result_json=?,updated_at=? WHERE batch_id=?",
                      (status, phase, _dump(result or {}), _now(), batch_id))
            if status in {"completed", "completed_noop"}:
                # 已提交后无需保留下载正文；永久保留任务摘要及主库提交凭据。
                c.execute("DELETE FROM downloads WHERE batch_id=?", (batch_id,))

    def get(self, batch_id):
        if not self.state_path.exists():
            return {"status": "not_found"}
        with closing(self._connect()) as c:
            row = c.execute("SELECT * FROM batches WHERE batch_id=?", (batch_id,)).fetchone()
        if row is None:
            return {"status": "not_found"}
        return {**dict(row), "request": json.loads(row["request_json"]),
                "result": json.loads(row["result_json"])}

    def list(self):
        if not self.state_path.exists():
            return []
        with closing(self._connect()) as c:
            ids = [r[0] for r in c.execute("SELECT batch_id FROM batches ORDER BY created_at DESC LIMIT 100")]
        return [self.get(key) for key in ids]

    def recover(self):
        if not self.worker_path.exists():
            return
        with closing(sqlite3.connect(self.worker_path, timeout=0)) as lock:
            try:
                lock.execute("BEGIN EXCLUSIVE")
            except sqlite3.OperationalError:
                return
            try:
                with closing(self._connect()) as c, c:
                    c.execute("UPDATE batches SET status='interrupted',phase='needs_attention' "
                              "WHERE status='running'")
            finally:
                lock.rollback()

    def start(self, batch_id):
        with self._lock:
            key = (str(self.database_path), batch_id)
            thread = self._threads.get(key)
            if thread and thread.is_alive():
                return self.get(batch_id)
            batch = self.get(batch_id)
            if batch["status"] in {"completed", "completed_noop"}:
                return batch
            if batch["status"] == "not_found":
                raise ValueError("更新任务不存在")
            if batch['status'] == 'expired':
                raise ValueError('下载缓存已过期，请新建更新任务')
            thread = threading.Thread(target=self.run, args=(batch_id,), daemon=True,
                                      name=batch_id)
            self._threads[key] = thread
            thread.start()
        return self.get(batch_id)

    def run(self, batch_id):
        self.ensure_schema()
        with closing(sqlite3.connect(self.worker_path, timeout=0)) as lock:
            try:
                lock.execute("BEGIN EXCLUSIVE")
            except sqlite3.OperationalError:
                return self.get(batch_id)
            try:
                return self._run_locked(batch_id)
            finally:
                lock.rollback()

    def _run_locked(self, batch_id):
        batch = self.get(batch_id)
        if batch["status"] in {"completed", "completed_noop"}:
            return batch
        if batch['status'] in {'expired', 'not_found'}:
            return batch
        request = batch["request"]
        self.update(batch_id, "running", "references")
        committed_result = None
        try:
            with maintenance_transaction(self.database_path) as connection:
                # 崩溃可能发生在主库提交后、任务状态写入前；先恢复已提交结果。
                connection.execute("CREATE TABLE IF NOT EXISTS maintenance_commits "
                                   "(batch_id TEXT PRIMARY KEY, data_version_id TEXT NOT NULL)")
                committed = connection.execute("SELECT data_version_id FROM maintenance_commits WHERE batch_id=?",
                                               (batch_id,)).fetchone()
                if committed:
                    result = {"data_version_id": committed[0], "recovered": True}
                else:
                    result = self._execute(batch_id, request, connection)
            committed_result = result
            self.update(batch_id, result.get("status", "completed"), "done", result)
        except Exception as error:
            self.update(batch_id, "failed", "needs_attention",
                        {"error": f"{type(error).__name__}: {error}",
                         "effective_data_unchanged": committed_result is None,
                         "committed_result": committed_result})
        return self.get(batch_id)

    def _execute(self, batch_id, request, connection):
        provider = DownloadCache(self.scheduler.provider, self, batch_id)
        scheduler = AShareSyncScheduler(
            self.database_path, provider=provider, max_workers=1,
            requests_per_minute=self.scheduler._rate_limiter.requests_per_minute,
            retry_count=self.scheduler.retry_count,
            base_backoff_seconds=self.scheduler.base_backoff_seconds,
            sleep=self.scheduler._sleep,
        )
        scheduler.ensure_schema()
        DataCenterStore(self.database_path).ensure_schema()
        # 事务共享一个连接，单线程按依赖执行，避免连接并发及中间批次生效。
        config = {
            "requests_per_minute": scheduler._rate_limiter.requests_per_minute,
            "retry_count": scheduler.retry_count,
            "backoff_seconds": scheduler.base_backoff_seconds,
            **request["effective_config"], "concurrency": 1,
        }
        scheduler._apply_effective_config(config)
        reference = scheduler.refresh_reference_data(end_date=request["target_trade_date"])
        target = reference.get("target_trade_date") or scheduler._latest_open_trade_date(request["target_trade_date"])
        if not target:
            raise ValueError("交易日历未覆盖目标日期")
        current = connection.execute("SELECT setting_value FROM data_center_settings WHERE setting_key='default_data_version_id'").fetchone()
        baseline = {"data_version_id": current[0] if current else None}
        frozen = self.cached(batch_id, "baseline")
        if frozen is not None and frozen != baseline:
            raise ValueError("当前数据已由另一任务更新，请新建更新任务，避免复用过时下载")
        if frozen is None:
            self.cache(batch_id, "baseline", baseline)
        self.update(batch_id, "running", "prices", {"target_trade_date": target})
        if request.get("existing_job_id"):
            job = scheduler.get_job(request["existing_job_id"])
        else:
            job = scheduler.create_job(target_trade_date=target, all_current=True,
                                       adjustments=["raw", "qfq", "hfq"], effective_config=config,
                                       schedule_key=batch_id)
        if job["status"] == "completed_noop":
            # 没有价格缺口时不制造版本；参考事实变化仍须经过同一质量门。
            if current and not any(reference.get(key) for key in ("catalog_count", "calendar_rows", "index_rows")):
                return {"status": "completed_noop", "target_trade_date": target}
            release = scheduler._validate_and_publish(job["job_id"])
        else:
            job = scheduler.run_job(job["job_id"])
            if job["status"] != "published":
                errors = [item.get("last_error") for item in job.get("items", []) if item.get("last_error")]
                raise ValueError("; ".join([job.get("last_error") or "数据检查未通过", *errors[:5]]))
            release = job
        self.update(batch_id, "running", "activating")
        version_id = release["data_version_id"]
        self._recheck_refetches(scheduler, job['job_id'], version_id, connection)
        # 指针、发布记录与事实在同一事务生效，不再要求人工设默认。
        connection.execute("INSERT INTO data_center_settings(setting_key,setting_value,updated_at) "
                           "VALUES ('default_data_version_id',?,?) ON CONFLICT(setting_key) DO UPDATE SET "
                           "setting_value=excluded.setting_value,updated_at=excluded.updated_at", (version_id, _now()))
        connection.execute("INSERT INTO maintenance_commits VALUES (?,?)", (batch_id, version_id))
        return {"status": "completed", "data_version_id": version_id, "target_trade_date": target,
                "quality_report_id": release["quality_report_id"], "rows_written": job.get("rows_written", 0)}

    def _recheck_refetches(self, scheduler, job_id, version_id, connection):
        """只复检用户已绑定至本任务的问题，不扩展到其他待处理修复。"""
        rows = connection.execute("""
            SELECT DISTINCT i.issue_id,i.source_task_id FROM data_quality_issues i
            JOIN data_quality_remediations r ON r.issue_id=i.issue_id
            WHERE r.executor_id=? AND r.status IN ('remediating','awaiting_recheck')
        """, (job_id,)).fetchall()
        if not rows:
            return
        from data_platform.quality_scan_engine import QualityScanEngine
        engine = QualityScanEngine(self.database_path, scheduler)
        for row in rows:
            if not connection.execute('SELECT 1 FROM data_quality_scan_jobs WHERE scan_id=?',
                                      (row['source_task_id'],)).fetchone():
                raise ValueError('修复缺少原始质量检查，不能自动生效')
            connection.execute("UPDATE data_quality_issues SET status='quarantined',workflow_status='awaiting_recheck' WHERE issue_id=?",
                               (row['issue_id'],))
        connection.execute("UPDATE data_quality_remediations SET status='awaiting_recheck',data_version_id=? "
                           "WHERE executor_id=? AND status IN ('remediating','awaiting_recheck')", (version_id, job_id))
        for parent in dict.fromkeys(row['source_task_id'] for row in rows):
            scan = engine.recheck(parent)
            if engine.run_scan(scan['scan_id'])['status'] != 'passed':
                raise ValueError('重拉后复检未通过，更新已撤回')
        if DataCenterStore(self.database_path).release_readiness()['status'] != 'ready':
            raise ValueError('修复后仍有阻断问题，更新已撤回')
        connection.execute("UPDATE data_quality_refetches SET status='published',completed_at=? WHERE task_id=?", (_now(), job_id))

    def run_existing(self, job_id):
        """兼容旧任务入口，但数据写入同样必须隔离并自动生效。"""
        self.scheduler.ensure_schema()
        job = self.scheduler.get_job(job_id)
        if job.get("status") in {"published", "completed_noop", "not_found"}:
            return job
        self.ensure_schema()
        batch_id = "maintenance-" + job_id
        request = {"target_trade_date": job["target_trade_date"],
                   "effective_config": job.get("effective_config") or {}, "existing_job_id": job_id}
        with closing(self._connect()) as c, c:
            c.execute("INSERT OR IGNORE INTO batches VALUES (?,?,'queued','queued','{}',?,?)",
                      (batch_id, _dump(request), _now(), _now()))
        result = self.run(batch_id)
        if result["status"] == "failed":
            self.scheduler._finish_job(job_id, status="failed", error=result["result"].get("error"))
        return self.scheduler.get_job(job_id, include_items=True)
