from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class LogEvent:
    message: str
    level: str = "info"


@dataclass
class ProgressEvent:
    current: int
    total: int
    mod_name: str = ""
    eta_seconds: float = 0.0


@dataclass
class BatchProgressEvent:
    mod_name: str
    batch_current: int
    batch_total: int
    strings_done: int
    strings_total: int
    cache_hits: int


@dataclass
class StateEvent:
    new_state: str


@dataclass
class ErrorEvent:
    exception: Exception
    context: str = ""


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable]] = {}
        self._lock = threading.Lock()
        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._tk_root = None

    def set_tk_root(self, root: Any) -> None:
        self._tk_root = root

    def subscribe(self, event_type: str, callback: Callable) -> None:
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(callback)

    def unsubscribe(self, event_type: str, callback: Callable) -> None:
        with self._lock:
            if event_type in self._subscribers:
                self._subscribers[event_type] = [
                    cb for cb in self._subscribers[event_type] if cb != callback
                ]

    def publish(self, event_type: str, data: Any = None) -> None:
        with self._lock:
            callbacks = list(self._subscribers.get(event_type, []))
        for callback in callbacks:
            try:
                callback(data)
            except Exception:
                pass

    def publish_threadsafe(self, event_type: str, data: Any = None) -> None:
        if self._tk_root is not None:
            self._tk_root.after(0, lambda: self.publish(event_type, data))
        else:
            self.publish(event_type, data)
