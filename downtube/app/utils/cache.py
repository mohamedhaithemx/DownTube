import time
import threading
import logging

logger = logging.getLogger(__name__)


class TTLCache:
    def __init__(self, ttl_seconds: int = 120):
        self._store: dict[str, tuple[float, object]] = {}
        self._ttl = ttl_seconds
        self._lock = threading.Lock()

    def get(self, key: str) -> object | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.time() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: object):
        with self._lock:
            self._store[key] = (time.time() + self._ttl, value)

    def delete(self, key: str):
        with self._lock:
            self._store.pop(key, None)

    def clear(self):
        with self._lock:
            self._store.clear()

    def cleanup(self):
        now = time.time()
        with self._lock:
            stale = [k for k, (exp, _) in self._store.items() if now > exp]
            for k in stale:
                del self._store[k]
            if stale:
                logger.debug("TTLCache: cleaned %d stale entries", len(stale))


info_cache = TTLCache(ttl_seconds=120)
