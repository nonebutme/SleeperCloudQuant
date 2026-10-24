"""R3 预注册、只读行情、可从冻结输入复算的标准因子研究。"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import random
import sqlite3
import statistics as st
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from _project_bootstrap import ensure_project_root_on_sys_path

ensure_project_root_on_sys_path()
from app.services.governed_point_in_time_universe import build_point_in_time_a_share_universe
from data_platform.maintenance_transaction import stable_research_read
from data_platform.research_data_version import ResearchDataVersionResolver
from factor_lab.research_core import calculate_factor, canonical_hash

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs/requirements/r3-standard-factor-protocol.md"
FACTORS = ("reversal_20d", "momentum_12_2", "low_volatility_20d")
NAMES = dict(zip(FACTORS, ("短期反转", "中期动量", "低波动")))
EXCLUDED = ("688", "689", "8", "43", "83", "87", "92", "900", "200")
CUTOFF = "2024-12-31"


def write_json(path, value):
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def snapshot(market, output):
    required = [("market_daily_prices", "qfq"), ("market_trade_calendar", ""),
                ("security_master_intervals", ""), ("security_lifecycle_events", ""),
                ("security_trading_status_daily", "")]
    with stable_research_read(market), closing(sqlite3.connect(
        f"file:{market.as_posix()}?mode=ro", uri=True
    )) as c:
        c.row_factory = sqlite3.Row
        c.execute("BEGIN")
        version = ResearchDataVersionResolver(market).resolve(required_members=required)
        if version["status"] != "ready":
            raise RuntimeError(json.dumps(version, ensure_ascii=False))
        member = next(m for m in version["required_members"] if m["dataset"] == "security_master_intervals")
        refs = set(json.loads(member["details_json"] or "{}").get("snapshot_refs", []))
        if member["sync_run_ref"]:
            refs.add(member["sync_run_ref"])
        if not refs:
            raise RuntimeError("point_in_time_snapshot_refs_missing")
        intervals = [dict(r) for r in c.execute(
            "SELECT * FROM security_master_intervals WHERE valid_from<=? "
            "AND COALESCE(valid_to,valid_from)>='2015-01-05'", (CUTOFF,))
            if json.loads(r["evidence_json"] or "{}").get("job_id") in refs]
        mother = sorted({r["symbol"] for r in intervals if not r["symbol"].startswith(EXCLUDED)},
                        key=lambda s: hashlib.sha256(("r3-v1:"+s).encode()).hexdigest())
        symbols = mother[:600]
        if len(symbols) < 600:
            raise RuntimeError("registered_sample_size_not_available")
        chosen = set(symbols)
        intervals = [r for r in intervals if r["symbol"] in chosen]
        calendar = [r[0] for r in c.execute(
            "SELECT trade_date FROM market_trade_calendar WHERE market='CN' AND is_open=1 "
            "AND trade_date BETWEEN '2015-01-05' AND ? ORDER BY trade_date", (CUTOFF,))]
        lifecycle = [dict(r) for r in c.execute("SELECT * FROM security_lifecycle_events WHERE effective_from<=?", (CUTOFF,))
                     if r["symbol"] in chosen]
        issues = [dict(r) for r in c.execute(
            "SELECT issue_id,symbol,observation_at,rule_id,workflow_status FROM data_quality_issues "
            "WHERE observation_at<? AND block_release=1", ("2025-01-01",)) if r["symbol"] in chosen]
        header = {"protocol_sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
                  "created_at": datetime.now(timezone.utc).isoformat(), "version": version,
                  "cutoff": CUTOFF, "mother_count": len(mother), "symbols": symbols,
                  "intervals": intervals, "lifecycle": lifecycle, "calendar": calendar,
                  "historical_quality_issues": issues,
                  "all_lifecycle_event_counts": [dict(r) for r in c.execute(
                      "SELECT event_type,count(*) n FROM security_lifecycle_events GROUP BY event_type")],
                  "price_columns": ["date", "open", "high", "low", "close", "volume", "is_tradable"]}
        write_json(output / "input_manifest.json", header)
        with gzip.open(output / "inputs.jsonl.gz", "xt", encoding="utf-8") as f:
            for n, symbol in enumerate(symbols):
                rows = [list(r) for r in c.execute(
                    "SELECT p.trade_date,p.open,p.high,p.low,p.close,p.volume,s.is_tradable "
                    "FROM market_daily_prices p LEFT JOIN security_trading_status_daily s "
                    "ON s.symbol=p.symbol AND s.trade_date=p.trade_date "
                    "WHERE p.symbol=? AND p.adjustment='qfq' "
                    "AND p.trade_date BETWEEN '2015-01-05' AND ? ORDER BY p.trade_date", (symbol, CUTOFF))]
                f.write(json.dumps({"symbol": symbol, "rows": rows}, separators=(",", ":"))+"\n")
                if (n+1) % 100 == 0:
                    print(f"snapshot {n+1}/{len(symbols)}", flush=True)
        current = ResearchDataVersionResolver(market).resolve(required_members=required)
        if current["data_version_id"] != version["data_version_id"]:
            raise RuntimeError("data_version_changed_during_snapshot")


def scores(closes):
    if len(closes) != 253 or any(x is None or not math.isfinite(x) or x <= 0 for x in closes):
        return None
    # 波动率复用现有计算内核；所有窗口均为同一市场日历，停牌不压缩日期。
    bars = [{"date": f"{i:03d}", "close": p} for i, p in enumerate(closes[-21:])]
    vol = calculate_factor("volatility_20d", bars)["020"]
    return (-(closes[-1]/closes[-21]-1), closes[-22]/closes[0]-1, -vol)


def executable(row):
    return bool(row and row[6] == 1 and row[5] is not None and row[5] > 0
                and all(x is not None and math.isfinite(x) and x > 0 for x in row[1:5])
                and row[2] > row[3] and row[3] <= row[1] <= row[2])


def outcome(entry, exit_row):
    if not executable(entry):
        return {"gross": 0.0, "net": 0.0, "stress": 0.0, "state": "cash_entry_unavailable"}
    if not executable(exit_row):
        return {"gross": None, "net": None, "stress": None, "state": "unknown_exit"}
    value = exit_row[1]/entry[1]-1
    return {"gross": value, "net": value-.002, "stress": value-.004, "state": "filled"}


def ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0]*len(values)
    start = 0
    while start < len(order):
        end = start+1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        for j in order[start:end]:
            out[j] = (start+end-1)/2
        start = end
    return out


def rank_ic(xs, ys):
    if len(xs) < 3 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    return st.correlation(ranks(xs), ranks(ys))


def average(rows, key):
    vals = [r[key] for r in rows]
    return st.fmean(vals) if vals and all(v is not None for v in vals) else None


def portfolio(rows):
    ordered = sorted(rows, key=lambda r: (r["score"], r["symbol"]))
    groups = [ordered[len(ordered)*i//5:len(ordered)*(i+1)//5] for i in range(5)]
    top = groups[-1]
    base = average(ordered, "gross")
    net = average(top, "net")
    stress = average(top, "stress")
    paired = [r for r in rows if r["state"] == "filled"]
    return {"n": len(rows), "groups_gross": [average(g, "gross") for g in groups],
            "top_net": net, "top_stress": stress, "benchmark_gross": base,
            "net_excess": net-base if net is not None and base is not None else None,
            "stress_excess": stress-base if stress is not None and base is not None else None,
            "rank_ic_complete_fills_only": rank_ic([r["score"] for r in paired], [r["gross"] for r in paired]),
            "unknown_exits": sum(r["state"] == "unknown_exit" for r in rows),
            "cash_entries": sum(r["state"] == "cash_entry_unavailable" for r in rows)}


def block_test(vals):
    if len(vals) < 24:
        return {"n": len(vals), "ci95": None, "p_one_sided": None}
    rng = random.Random(314159)
    means = []
    for _ in range(3000):
        drawn = []
        while len(drawn) < len(vals):
            start = rng.randrange(len(vals))
            drawn.extend(vals[(start+j) % len(vals)] for j in range(6))
        means.append(st.fmean(drawn[:len(vals)]))
    mean = st.fmean(vals)
    means.sort()
    return {"n": len(vals), "ci95": [means[74], means[2924]],
            "p_one_sided": (1+sum(m-mean >= mean for m in means))/3001}


def performance(values):
    if not values or any(v is None for v in values):
        return None
    nav = peak = 1.0
    drawdown = 0.0
    for value in values:
        nav *= 1+value
        peak = max(peak, nav)
        drawdown = min(drawdown, nav/peak-1)
    return {"cumulative": nav-1, "annualized_252_20": nav**(252/(20*len(values)))-1,
            "period_end_max_drawdown": drawdown,
            "annualized_period_vol": st.pstdev(values)*math.sqrt(252/20)}


def summarize(periods):
    usable = [r for r in periods if r["net_excess"] is not None]
    vals = [r["net_excess"] for r in usable]
    yearly = {}
    for year in sorted({r["signal"][:4] for r in periods}):
        ys = [r for r in periods if r["signal"].startswith(year)]
        known = [r["net_excess"] for r in ys if r["net_excess"] is not None]
        yearly[year] = {"periods": len(ys), "known_periods": len(known),
                        "mean_net_excess": st.fmean(known) if known else None}
    return {"periods": len(periods), "known_periods": len(usable),
            "mean_net_excess": st.fmean(vals) if vals else None,
            "mean_stress_excess": st.fmean(r["stress_excess"] for r in usable) if usable else None,
            "mean_groups_gross_complete_periods": [st.fmean(r["groups_gross"][i] for r in usable) for i in range(5)] if usable else None,
            "mean_rank_ic_complete_fills_only": st.fmean(r["rank_ic_complete_fills_only"] for r in periods if r["rank_ic_complete_fills_only"] is not None) if periods else None,
            "top_net_performance": performance([r["top_net"] for r in periods]),
            "benchmark_performance": performance([r["benchmark_gross"] for r in periods]),
            "unknown_exit_observations": sum(r["unknown_exits"] for r in periods),
            "cash_entry_observations": sum(r["cash_entries"] for r in periods),
            "block_bootstrap": block_test(vals), "yearly": yearly}


def analyze(source, output):
    manifest = json.loads((source/"input_manifest.json").read_text(encoding="utf-8"))
    if manifest["protocol_sha256"] != hashlib.sha256(PROTOCOL.read_bytes()).hexdigest():
        raise RuntimeError("frozen_protocol_changed")
    if manifest["cutoff"] != CUTOFF:
        raise RuntimeError("sealed_sample_cutoff_mismatch")
    calendar = manifest["calendar"]
    if max(calendar) > CUTOFF:
        raise RuntimeError("sealed_sample_calendar_violation")
    start = next(i for i, d in enumerate(calendar) if d >= "2016-01-04")
    indices = [i for i in range(start, len(calendar)-21, 20) if calendar[i] <= "2024-11-29"]
    eligibility = {}
    gate_issues = []
    for i in indices:
        result = build_point_in_time_a_share_universe(manifest["intervals"], as_of_date=calendar[i], structural_exclusion_prefixes=EXCLUDED)
        if not result["ok"]:
            gate_issues.append({"date": calendar[i], "issues": result["issues"]})
        eligibility[calendar[i]] = {r["symbol"] for r in result["eligible"]}
    if gate_issues:
        write_json(output/"blocked_universe.json", gate_issues)
        raise RuntimeError("point_in_time_universe_gate_failed; see blocked_universe.json")
    lifecycle = defaultdict(list)
    for row in manifest["lifecycle"]:
        lifecycle[row["symbol"]].append(row)
    samples = {s: i % 2 for i, s in enumerate(manifest["symbols"])}
    panels = {factor: defaultdict(list) for factor in FACTORS}
    observation_count = 0
    with gzip.open(source/"inputs.jsonl.gz", "rt", encoding="utf-8") as f:
        for number, line in enumerate(f):
            item = json.loads(line)
            symbol = item["symbol"]
            rows = item["rows"]
            if any(r[0] > CUTOFF for r in rows):
                raise RuntimeError("sealed_sample_price_violation")
            prices = {r[0]: r for r in rows}
            for i in indices:
                date = calendar[i]
                if i < 252 or symbol not in eligibility[date]:
                    continue
                events = lifecycle[symbol]
                if not any(e["event_type"] in {"listed", "listed_source_observation"} and e["effective_from"] <= date
                           and (not e["effective_to"] or e["effective_to"] >= date) for e in events):
                    continue
                if any(e["event_type"].lower().startswith("delist") and e["effective_from"] <= date for e in events):
                    continue
                history = [prices.get(d) for d in calendar[i-252:i+1]]
                if any(r is None for r in history):
                    continue
                values = scores([r[4] for r in history])
                if values is None:
                    continue
                future = outcome(prices.get(calendar[i+1]), prices.get(calendar[i+21]))
                for factor, value in zip(FACTORS, values):
                    panels[factor][date].append({"symbol": symbol, "score": value, "sample": samples[symbol], **future})
                observation_count += 1
            if (number+1) % 100 == 0:
                print(f"analyze {number+1}/{len(samples)}", flush=True)
    results = {}
    with gzip.open(output/"observations.jsonl.gz", "xt", encoding="utf-8") as f:
        for factor in FACTORS:
            periods = []
            replicas = {0: [], 1: []}
            for i in indices:
                date = calendar[i]
                rows = panels[factor][date]
                if len(rows) < 50:
                    continue
                # 组别只依赖已知信号；未知未来收益不改变成员。
                ordered = sorted(rows, key=lambda r: (r["score"], r["symbol"]))
                for group in range(5):
                    for row in ordered[len(rows)*group//5:len(rows)*(group+1)//5]:
                        f.write(json.dumps({"factor": factor, "signal": date, "entry": calendar[i+1],
                                            "exit": calendar[i+21], "group": group+1, **row}, separators=(",", ":"))+"\n")
                periods.append({"signal": date, "entry": calendar[i+1], "exit": calendar[i+21], **portfolio(rows)})
                for sample in replicas:
                    subset = [r for r in rows if r["sample"] == sample]
                    if len(subset) >= 25:
                        replicas[sample].append({"signal": date, **portfolio(subset)})
            write_json(output/(factor+"_periods.json"), periods)
            results[factor] = {"name": NAMES[factor], "development": summarize([r for r in periods if r["signal"] < "2021"]),
                               "holdout": summarize([r for r in periods if r["signal"] >= "2021"]),
                               "replicas_holdout": {str(k): summarize([r for r in v if r["signal"] >= "2021"]) for k, v in replicas.items()}}
    running = 0.0
    for rank, factor in enumerate(sorted(FACTORS, key=lambda k: results[k]["holdout"]["block_bootstrap"]["p_one_sided"] or 1)):
        p = results[factor]["holdout"]["block_bootstrap"]["p_one_sided"]
        running = max(running, min(1, (3-rank)*(p if p is not None else 1)))
        # 未达到最少期数时没有 p 值，不能把保守占位值 1 冒充统计结果。
        results[factor]["holdout"]["holm_p"] = running if p is not None else None
    for factor in FACTORS:
        h = results[factor]["holdout"]
        checks = {"positive_net_excess": (h["mean_net_excess"] or 0) > 0,
                  "holm_below_005": h["holm_p"] is not None and h["holm_p"] < .05,
                  "stress_positive": (h["mean_stress_excess"] or 0) > 0,
                  "three_positive_years": sum((v["mean_net_excess"] or 0) > 0 for v in h["yearly"].values()) >= 3,
                  "two_stock_replicas_positive": all((v["mean_net_excess"] or 0) > 0 for v in results[factor]["replicas_holdout"].values()),
                  "no_unknown_holdout_exits": h["unknown_exit_observations"] == 0,
                  "historical_universe_completeness_verified": False,
                  "executable_account_backtest_verified": False}
        results[factor]["acceptance_checks"] = checks
        results[factor]["accepted"] = all(checks.values())
    report = {"protocol_sha256": manifest["protocol_sha256"], "input_manifest_hash": canonical_hash(manifest),
              "data_version_id": manifest["version"]["data_version_id"], "mother_count": manifest["mother_count"],
              "sample_count": len(samples), "common_signal_observations": observation_count,
              "factors": results, "accepted_patterns": sum(r["accepted"] for r in results.values()),
              "status": "research_completed_acceptance_not_met"}
    write_json(output/"results.json", report)
    print(json.dumps({"status": report["status"], "accepted_patterns": report["accepted_patterns"],
                      "observations": observation_count, "results": str(output/"results.json")}, ensure_ascii=True), flush=True)


def verify_snapshot(source):
    hashes = json.loads((source/"sha256.json").read_text(encoding="utf-8"))
    for name in ("input_manifest.json", "inputs.jsonl.gz"):
        if hashlib.sha256((source/name).read_bytes()).hexdigest() != hashes.get(name):
            raise RuntimeError("frozen_input_hash_mismatch:"+name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-database", type=Path, default=ROOT/"var/market/a_share_market.sqlite3")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replay", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    write_json(output/"run_registration.json", {"protocol_sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
                                               "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                               "created_at": datetime.now(timezone.utc).isoformat(), "factors": FACTORS})
    if args.replay:
        source = args.replay.resolve()
        verify_snapshot(source)
    else:
        snapshot(args.market_database.resolve(), output)
        source = output
    analyze(source, output)
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
    write_json(output/"sha256.json", hashes)


if __name__ == "__main__":
    main()
