"""In-memory metrics, logs, and feedback store powering the Phase 3 dashboard."""

import threading
import time
from collections import deque
from typing import Dict, List


class MetricsStore:
    def __init__(self, slo_error_rate: float = 0.05, slo_p95_ms: int = 2000):
        self._lock = threading.Lock()
        self._requests: List[dict] = []
        self._feedback: List[dict] = []
        self._logs: deque = deque(maxlen=300)
        self._started = time.time()
        self.slo_error_rate = slo_error_rate
        self.slo_p95_ms = slo_p95_ms

    # -- recording ----------------------------------------------------------

    def record_request(self, **entry) -> None:
        entry.setdefault("ts", time.time())
        with self._lock:
            self._requests.append(entry)

    def record_feedback(self, entry: dict) -> int:
        entry.setdefault("ts", time.time())
        with self._lock:
            self._feedback.append(entry)
            return len(self._feedback)

    def log(self, level: str, message: str) -> None:
        with self._lock:
            self._logs.append({"ts": time.time(), "level": level, "message": message})

    # -- aggregation --------------------------------------------------------

    def _snapshot(self) -> List[dict]:
        with self._lock:
            return list(self._requests)

    def uptime_seconds(self) -> int:
        return int(time.time() - self._started)

    def analytics(self) -> dict:
        reqs = self._snapshot()
        total = len(reqs)
        if total == 0:
            return {
                "total_requests": 0, "success_rate": None, "avg_latency_ms": None,
                "total_cost_usd": 0.0, "cache_hit_rate": 0.0, "fallback_rate": None,
                "by_model": {}, "by_tier": {}, "by_query_type": {},
                "requests_per_minute": [],
            }

        by_model: Dict[str, dict] = {}
        by_tier: Dict[str, int] = {}
        by_type: Dict[str, int] = {}
        for r in reqs:
            m = by_model.setdefault(
                r["model"],
                {"requests": 0, "success": 0, "latency_sum": 0, "cost_usd": 0.0, "tokens": 0},
            )
            m["requests"] += 1
            m["success"] += 1 if r["success"] else 0
            m["latency_sum"] += r["latency_ms"]
            m["cost_usd"] += r["cost_usd"]
            m["tokens"] += r["tokens_total"]
            by_tier[r["user_tier"]] = by_tier.get(r["user_tier"], 0) + 1
            by_type[r["query_type"]] = by_type.get(r["query_type"], 0) + 1

        models = {
            name: {
                "requests": m["requests"],
                "success_rate": round(m["success"] / m["requests"], 4),
                "avg_latency_ms": round(m["latency_sum"] / m["requests"], 2),
                "total_cost_usd": round(m["cost_usd"], 8),
                "total_tokens": m["tokens"],
                "cost_per_1k_tokens": round(m["cost_usd"] / m["tokens"] * 1000, 8) if m["tokens"] else 0.0,
            }
            for name, m in by_model.items()
        }

        now = time.time()
        buckets: Dict[int, int] = {}
        for r in reqs:
            age_min = int((now - r["ts"]) // 60)
            if age_min < 30:
                buckets[age_min] = buckets.get(age_min, 0) + 1

        return {
            "total_requests": total,
            "success_rate": round(sum(1 for r in reqs if r["success"]) / total, 4),
            "avg_latency_ms": round(sum(r["latency_ms"] for r in reqs) / total, 2),
            "total_cost_usd": round(sum(r["cost_usd"] for r in reqs), 8),
            "cache_hit_rate": round(sum(1 for r in reqs if r.get("cached")) / total, 4),
            "fallback_rate": round(sum(1 for r in reqs if r["fallback_used"]) / total, 4),
            "by_model": models,
            "by_tier": {t: {"requests": n, "share": round(n / total, 4)} for t, n in by_tier.items()},
            "by_query_type": by_type,
            "requests_per_minute": [
                {"minutes_ago": m, "requests": buckets.get(m, 0)} for m in range(29, -1, -1)
            ],
        }

    def quality_dashboard(self) -> dict:
        reqs = self._snapshot()
        total = len(reqs)
        latencies = sorted(r["latency_ms"] for r in reqs)
        p95 = latencies[max(0, int(len(latencies) * 0.95) - 1)] if latencies else None
        errors = sum(1 for r in reqs if not r["success"])
        error_rate = round(errors / total, 4) if total else None
        fallback = sum(1 for r in reqs if r["fallback_used"])

        counts: Dict[str, int] = {}
        for r in reqs:
            counts[r["model"]] = counts.get(r["model"], 0) + 1
        hotspots = sorted(
            ({"model": m, "requests": n, "share": round(n / total, 4)} for m, n in counts.items()),
            key=lambda x: -x["requests"],
        )[:3]

        alerts = []
        if total and error_rate > self.slo_error_rate:
            alerts.append({
                "severity": "critical",
                "message": f"Error rate {error_rate:.1%} exceeds SLO target {self.slo_error_rate:.0%}",
            })
        if p95 is not None and p95 > self.slo_p95_ms:
            alerts.append({
                "severity": "warning",
                "message": f"P95 latency {p95}ms exceeds SLO target {self.slo_p95_ms}ms",
            })
        if total and fallback / total > 0.5:
            alerts.append({
                "severity": "warning",
                "message": f"Fallback used on {fallback}/{total} requests, check provider API keys",
            })

        return {
            "requests_total": total,
            "success_rate": round(1 - errors / total, 4) if total else None,
            "error_rate": error_rate,
            "avg_latency_ms": round(sum(latencies) / total, 2) if total else None,
            "p95_latency_ms": p95,
            "fallback_count": fallback,
            "hotspots": hotspots,
            "slo": {
                "error_rate_target": self.slo_error_rate,
                "p95_latency_target_ms": self.slo_p95_ms,
                "compliant": (
                    (error_rate <= self.slo_error_rate and (p95 is None or p95 <= self.slo_p95_ms))
                    if total else None
                ),
            },
            "alerts": alerts,
            "feedback_count": len(self._feedback),
        }

    def recent_logs(self, limit: int = 100) -> List[dict]:
        with self._lock:
            return list(self._logs)[-limit:]
