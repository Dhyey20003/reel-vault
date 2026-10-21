"""A tiny in-process background job runner so slow work never blocks the UI."""
from __future__ import annotations

import logging
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

log = logging.getLogger("reelvault.jobs")


class JobRunner:
    def __init__(self, workers: int = 3):
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="rv-job")
        self._lock = threading.Lock()
        self._inflight: set[str] = set()

    def submit(self, key: str, fn: Callable[[], None]) -> bool:
        """Runs fn in the background unless a job with the same key is already in flight."""
        with self._lock:
            if key in self._inflight:
                return False
            self._inflight.add(key)

        def wrapper() -> None:
            try:
                fn()
            except Exception:  # noqa: BLE001 - background jobs must never crash the server
                log.error("job %s failed:\n%s", key, traceback.format_exc())
            finally:
                with self._lock:
                    self._inflight.discard(key)

        self._pool.submit(wrapper)
        return True

    def is_running(self, key: str) -> bool:
        with self._lock:
            return key in self._inflight

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
