from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass
import os
from typing import Callable, Literal, Sequence, TypeVar


T = TypeVar("T")
R = TypeVar("R")

ThreadMode = Literal["serial", "threads", "processes", "auto"]


@dataclass(frozen=True)
class ThreadContext:
    """Shared-memory execution context with a serial fallback."""

    mode: ThreadMode = "serial"
    workers: int = 1
    chunk_size: int | None = None

    @property
    def active(self) -> bool:
        return self.mode in {"threads", "processes"} and self.workers > 1

    def map(self, fn: Callable[[T], R], items: Sequence[T]) -> list[R]:
        if not self.active or len(items) <= 1:
            return [fn(item) for item in items]
        if self.mode == "processes":
            with ProcessPoolExecutor(max_workers=self.workers) as pool:
                return list(pool.map(fn, items, chunksize=self.chunk_size or 1))
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            return list(pool.map(fn, items))


def get_thread_context(mode: ThreadMode = "auto", workers: int | None = None) -> ThreadContext:
    """Return a deterministic shared-memory context.

    ``auto`` reads ``SPRITZ_THREADS`` before falling back to ``os.cpu_count``.
    The returned context is serial when the selected worker count is one.
    """

    normalized = str(mode or "auto").strip().lower()
    if normalized not in {"serial", "threads", "processes", "auto"}:
        raise ValueError("thread backend must be serial, threads, processes, or auto")
    if normalized == "serial":
        return ThreadContext("serial", 1)

    cpu_count = os.cpu_count() or 1
    env_workers = int(os.environ.get("SPRITZ_THREADS", "0") or 0)
    selected = max(1, int(workers or env_workers or cpu_count))
    if normalized == "auto":
        normalized = "threads" if selected > 1 else "serial"
    return ThreadContext(normalized, selected)
