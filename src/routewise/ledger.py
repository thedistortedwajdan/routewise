"""SQLite ledger: one row per request, the source of truth for cost reporting."""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    tier TEXT NOT NULL,
    model TEXT NOT NULL,
    route_reason TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    est_strong_cost_usd REAL NOT NULL,
    latency_ms INTEGER NOT NULL,
    status TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_requests_ts ON requests(ts);
"""


@dataclass(frozen=True)
class Record:
    id: str
    tier: str
    model: str
    route_reason: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    est_strong_cost_usd: float
    latency_ms: int
    status: str = "ok"


class Ledger:
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)

    def add(self, r: Record, ts: float | None = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    r.id,
                    ts if ts is not None else time.time(),
                    r.tier,
                    r.model,
                    r.route_reason,
                    r.input_tokens,
                    r.output_tokens,
                    r.cost_usd,
                    r.est_strong_cost_usd,
                    r.latency_ms,
                    r.status,
                ),
            )
            self._conn.commit()

    def spend_since(self, since_ts: float) -> float:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM requests WHERE ts >= ?", (since_ts,)
            ).fetchone()
        return float(row[0])

    def summary(self) -> dict:
        with self._lock:
            rows = self._conn.execute(
                "SELECT tier, COUNT(*), SUM(input_tokens), SUM(output_tokens), SUM(cost_usd),"
                " SUM(est_strong_cost_usd) FROM requests GROUP BY tier"
            ).fetchall()
        tiers = {
            t: {
                "requests": n,
                "input_tokens": i,
                "output_tokens": o,
                "cost_usd": round(c, 6),
                "est_strong_cost_usd": round(e, 6),
            }
            for t, n, i, o, c, e in rows
        }
        total = sum(v["cost_usd"] for v in tiers.values())
        est = sum(v["est_strong_cost_usd"] for v in tiers.values())
        return {
            "tiers": tiers,
            "total_cost_usd": round(total, 6),
            "est_all_strong_cost_usd": round(est, 6),
            "note": "est_all_strong is an estimate: the same tokens priced at the strong "
            "tier. Real comparisons come from the replay harness.",
        }
