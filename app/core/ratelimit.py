import threading
import time
from collections import defaultdict


class RateLimiter:
    """Sliding-window in-memory rate limiter (per key)."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = [t for t in self._hits[key] if now - t < window_seconds]
            if len(bucket) >= limit:
                self._hits[key] = bucket
                return False
            bucket.append(now)
            self._hits[key] = bucket
            return True

    def retry_after(self, key: str, window_seconds: int) -> int:
        with self._lock:
            hits = self._hits.get(key, [])
            if not hits:
                return 0
            oldest = min(hits)
            return max(0, int(window_seconds - (time.monotonic() - oldest)))


rate_limiter = RateLimiter()
