from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Literal

from vibecoding_board.request_log import UsageLogEntry


MetricsWindow = Literal["24h", "7d"]

WINDOW_HOURS: dict[MetricsWindow, int] = {
    "24h": 24,
    "7d": 24 * 7,
}


@dataclass(slots=True)
class ProviderMetricsSummary:
    requests: int = 0
    total_tokens: int = 0


@dataclass(slots=True)
class HourlyMetricsBucket:
    bucket_start: datetime
    requests: int = 0
    success_count: int = 0
    interrupted_count: int = 0
    error_count: int = 0
    total_tokens: int = 0
    duration_sum_ms: int = 0
    duration_count: int = 0
    ttfb_sum_ms: int = 0
    ttfb_count: int = 0
    providers: dict[str, ProviderMetricsSummary] = field(default_factory=dict)

    def average_duration_ms(self) -> float | None:
        if not self.duration_count:
            return None
        return round(self.duration_sum_ms / self.duration_count, 2)

    def average_ttfb_ms(self) -> float | None:
        if not self.ttfb_count:
            return None
        return round(self.ttfb_sum_ms / self.ttfb_count, 2)

    def success_rate(self) -> float | None:
        if not self.requests:
            return None
        return round(self.success_count / self.requests, 4)

    def to_dict(self) -> dict[str, object]:
        return {
            "bucket_start": self.bucket_start.isoformat(),
            "requests": self.requests,
            "success_count": self.success_count,
            "interrupted_count": self.interrupted_count,
            "error_count": self.error_count,
            "total_tokens": self.total_tokens,
            "duration_sum_ms": self.duration_sum_ms,
            "duration_count": self.duration_count,
            "ttfb_sum_ms": self.ttfb_sum_ms,
            "ttfb_count": self.ttfb_count,
            "providers": {
                provider_name: {
                    "requests": summary.requests,
                    "total_tokens": summary.total_tokens,
                }
                for provider_name, summary in self.providers.items()
            },
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "HourlyMetricsBucket":
        providers = {
            provider_name: ProviderMetricsSummary(
                requests=int(summary.get("requests", 0)),
                total_tokens=int(summary.get("total_tokens", 0)),
            )
            for provider_name, summary in (payload.get("providers") or {}).items()
            if isinstance(provider_name, str) and isinstance(summary, dict)
        }
        return cls(
            bucket_start=datetime.fromisoformat(str(payload["bucket_start"])).astimezone(),
            requests=int(payload.get("requests", 0)),
            success_count=int(payload.get("success_count", 0)),
            interrupted_count=int(payload.get("interrupted_count", 0)),
            error_count=int(payload.get("error_count", 0)),
            total_tokens=int(payload.get("total_tokens", 0)),
            duration_sum_ms=int(payload.get("duration_sum_ms", 0)),
            duration_count=int(payload.get("duration_count", 0)),
            ttfb_sum_ms=int(payload.get("ttfb_sum_ms", 0)),
            ttfb_count=int(payload.get("ttfb_count", 0)),
            providers=providers,
        )


class AdminMetricsStore:
    def __init__(
        self,
        path: str | Path,
        *,
        retention_hours: int = 24 * 30,
        flush_interval_seconds: float = 30.0,
    ) -> None:
        self.path = Path(path).resolve()
        self.retention_hours = retention_hours
        self.flush_interval_seconds = flush_interval_seconds
        self.last_flushed_at: datetime | None = None
        self._buckets: dict[str, HourlyMetricsBucket] = {}
        self._dirty = False
        self._flush_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    def load(self) -> None:
        try:
            raw_content = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return

        try:
            payload = json.loads(raw_content)
        except json.JSONDecodeError:
            return
        self.last_flushed_at = (
            datetime.fromisoformat(payload["last_flushed_at"]).astimezone()
            if payload.get("last_flushed_at")
            else None
        )
        buckets = payload.get("buckets", [])
        if not isinstance(buckets, list):
            return
        loaded_buckets = [HourlyMetricsBucket.from_dict(item) for item in buckets if isinstance(item, dict)]
        self._buckets = {
            bucket.bucket_start.isoformat(): bucket
            for bucket in loaded_buckets
        }
        self._trim_stale_buckets(datetime.now().astimezone())

    async def close(self) -> None:
        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None
        await self.flush()

    async def record_request(
        self,
        *,
        final_provider: str | None,
        state: str,
        duration_ms: int | None,
        ttfb_ms: int | None,
        usage: UsageLogEntry | None,
        completed_at: datetime | None = None,
    ) -> None:
        timestamp = (completed_at or datetime.now().astimezone()).astimezone()
        bucket_start = timestamp.replace(minute=0, second=0, microsecond=0)
        bucket_key = bucket_start.isoformat()
        total_tokens = 0 if usage is None else usage.total_tokens or 0

        async with self._lock:
            bucket = self._buckets.get(bucket_key)
            if bucket is None:
                bucket = HourlyMetricsBucket(bucket_start=bucket_start)
                self._buckets[bucket_key] = bucket

            bucket.requests += 1
            if state == "success":
                bucket.success_count += 1
            elif state == "interrupted":
                bucket.interrupted_count += 1
            else:
                bucket.error_count += 1

            bucket.total_tokens += total_tokens
            if duration_ms is not None:
                bucket.duration_sum_ms += duration_ms
                bucket.duration_count += 1
            if ttfb_ms is not None:
                bucket.ttfb_sum_ms += ttfb_ms
                bucket.ttfb_count += 1

            if final_provider is not None:
                provider_summary = bucket.providers.setdefault(final_provider, ProviderMetricsSummary())
                provider_summary.requests += 1
                provider_summary.total_tokens += total_tokens

            self._trim_stale_buckets(timestamp)
            self._dirty = True

        self._schedule_flush()

    async def flush(self) -> None:
        async with self._lock:
            if not self._dirty:
                return
            buckets = sorted(self._buckets.values(), key=lambda bucket: bucket.bucket_start)
            payload = {
                "last_flushed_at": datetime.now().astimezone().isoformat(),
                "retention_hours": self.retention_hours,
                "buckets": [bucket.to_dict() for bucket in buckets],
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.last_flushed_at = datetime.fromisoformat(payload["last_flushed_at"]).astimezone()
            self._dirty = False

    async def metrics_payload(self, *, window: MetricsWindow) -> dict[str, object]:
        hours = WINDOW_HOURS[window]
        now = datetime.now().astimezone().replace(minute=0, second=0, microsecond=0)
        bucket_starts = [now - timedelta(hours=offset) for offset in reversed(range(hours))]
        bucket_keys = [bucket_start.isoformat() for bucket_start in bucket_starts]

        async with self._lock:
            buckets = {key: self._buckets.get(key) for key in bucket_keys}

        request_points = []
        token_points = []
        duration_points = []
        success_points = []
        ttfb_points = []

        total_requests = 0
        total_tokens = 0
        total_success = 0
        duration_sum = 0
        duration_count = 0
        state_counts = {"success": 0, "interrupted": 0, "error": 0}
        provider_totals: dict[str, ProviderMetricsSummary] = {}

        for bucket_start, bucket_key in zip(bucket_starts, bucket_keys, strict=True):
            bucket = buckets[bucket_key]
            requests = bucket.requests if bucket is not None else 0
            tokens = bucket.total_tokens if bucket is not None else 0
            average_duration = bucket.average_duration_ms() if bucket is not None else None
            success_rate = bucket.success_rate() if bucket is not None else None
            average_ttfb = bucket.average_ttfb_ms() if bucket is not None else None

            request_points.append(self._point(bucket_start, requests))
            token_points.append(self._point(bucket_start, tokens))
            duration_points.append(self._point(bucket_start, average_duration))
            success_points.append(self._point(bucket_start, success_rate))
            ttfb_points.append(self._point(bucket_start, average_ttfb))

            if bucket is None:
                continue

            total_requests += bucket.requests
            total_tokens += bucket.total_tokens
            total_success += bucket.success_count
            duration_sum += bucket.duration_sum_ms
            duration_count += bucket.duration_count
            state_counts["success"] += bucket.success_count
            state_counts["interrupted"] += bucket.interrupted_count
            state_counts["error"] += bucket.error_count

            for provider_name, summary in bucket.providers.items():
                provider_total = provider_totals.setdefault(provider_name, ProviderMetricsSummary())
                provider_total.requests += summary.requests
                provider_total.total_tokens += summary.total_tokens

        provider_breakdown = [
            {
                "provider_name": provider_name,
                "requests": summary.requests,
                "total_tokens": summary.total_tokens,
            }
            for provider_name, summary in sorted(
                provider_totals.items(),
                key=lambda item: (-item[1].requests, item[0]),
            )
        ]

        return {
            "window": window,
            "metrics_path": str(self.path),
            "last_flushed_at": self.last_flushed_at,
            "summary": {
                "requests": total_requests,
                "total_tokens": total_tokens,
                "average_duration_ms": round(duration_sum / duration_count, 2) if duration_count else None,
                "success_rate": round(total_success / total_requests, 4) if total_requests else None,
            },
            "timeseries": {
                "requests": request_points,
                "tokens": token_points,
                "duration_ms": duration_points,
                "success_rate": success_points,
                "average_ttfb_ms": ttfb_points,
            },
            "breakdowns": {
                "providers": provider_breakdown,
                "states": [
                    {"state": "success", "count": state_counts["success"]},
                    {"state": "interrupted", "count": state_counts["interrupted"]},
                    {"state": "error", "count": state_counts["error"]},
                ],
            },
        }

    def _schedule_flush(self) -> None:
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._flush_after_delay())

    async def _flush_after_delay(self) -> None:
        try:
            await asyncio.sleep(self.flush_interval_seconds)
            await self.flush()
        except asyncio.CancelledError:
            raise

    def _trim_stale_buckets(self, reference_time: datetime) -> None:
        cutoff = reference_time - timedelta(hours=self.retention_hours)
        self._buckets = {
            key: bucket
            for key, bucket in self._buckets.items()
            if bucket.bucket_start >= cutoff
        }

    @staticmethod
    def _point(bucket_start: datetime, value: int | float | None) -> dict[str, object]:
        return {
            "bucket_start": bucket_start.isoformat(),
            "value": value,
        }
