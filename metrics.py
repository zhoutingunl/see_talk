"""成本 / QoS 实测对账(design.md §14/§15/§16/§19)。

SQLite 记录每轮调用与埋点事件,Dashboard 据此算:
- 实际 token vs Baseline(朴素实现每轮整图)token → 节省率(实测,非拍脑袋)
- 延迟按回合类型分桶(纯文本 / 带图)→ P50 / P95
- 成本估算(单价可配,明确标注"估算")
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

# Baseline:朴素实现每轮发整图的图片 token(design.md §14)
BASELINE_IMAGE_TOKENS = 1300
# 估算单价(每 1K token,人民币;占位,真实以账单为准)
PRICE_IN_PER_1K = 0.0012
PRICE_OUT_PER_1K = 0.0012


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))
    return round(s[k], 1)


class MetricsStore:
    def __init__(self, db_path: str = "seetalk.db"):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS turns(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT,
                    session_id TEXT, turn_type TEXT, route TEXT, source TEXT,
                    cache_hit INTEGER, input_tokens INTEGER, output_tokens INTEGER,
                    latency_ms REAL)""")
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, name TEXT, data TEXT)""")

    # ---- 写入 ----
    def record_turn(self, *, session_id: str = "", turn_type: str = "image",
                    route: str = "image", source: str = "minimax",
                    cache_hit: bool = False, input_tokens: int = 0,
                    output_tokens: int = 0, latency_ms: float = 0.0) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO turns(ts,session_id,turn_type,route,source,cache_hit,"
                "input_tokens,output_tokens,latency_ms) VALUES(?,?,?,?,?,?,?,?,?)",
                (_now(), session_id, turn_type, route, source, int(cache_hit),
                 input_tokens, output_tokens, latency_ms))

    def track(self, name: str, data: dict | None = None) -> None:
        """埋点(design.md §19)。"""
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO events(ts,name,data) VALUES(?,?,?)",
                               (_now(), name, json.dumps(data or {}, ensure_ascii=False)))

    # ---- 汇总(Dashboard)----
    def summary(self) -> dict:
        rows = self._conn.execute("SELECT * FROM turns").fetchall()
        total = len(rows)
        cache_hits = sum(r["cache_hit"] for r in rows)
        in_tok = sum(r["input_tokens"] for r in rows)
        out_tok = sum(r["output_tokens"] for r in rows)

        # Baseline:朴素实现假设每轮都发整图
        baseline_in = total * BASELINE_IMAGE_TOKENS
        savings = (1 - in_tok / baseline_in) if baseline_in else 0.0

        lat = {"text": [], "image": []}
        for r in rows:
            lat.setdefault(r["turn_type"], lat["image"]).append(r["latency_ms"])
        latency = {t: {"p50": _percentile(v, 50), "p95": _percentile(v, 95), "n": len(v)}
                   for t, v in lat.items() if v}

        cost = round(in_tok / 1000 * PRICE_IN_PER_1K
                     + out_tok / 1000 * PRICE_OUT_PER_1K, 4)
        ev_total = self._conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]

        return {
            "turns": total,
            "cache_hits": cache_hits,
            "cache_hit_rate": round(cache_hits / total, 3) if total else 0.0,
            "actual_input_tokens": in_tok,
            "output_tokens": out_tok,
            "baseline_input_tokens": baseline_in,
            "savings_rate": round(max(0.0, savings), 3),
            "latency_ms": latency,
            "cost_estimate_cny": cost,
            "events": ev_total,
        }

    def reset(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM turns")
            self._conn.execute("DELETE FROM events")


_store: MetricsStore | None = None


def get_store() -> MetricsStore:
    global _store
    if _store is None:
        _store = MetricsStore(os.getenv("SEETALK_DB", "seetalk.db"))
    return _store
