from __future__ import annotations

import threading
import time

from src.core.events import EventBus, ProgressEvent, StateEvent
from src.core.models import PipelineState


class CancelledError(Exception):
    pass


class ProgressTracker:
    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self.state = PipelineState.IDLE
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._cancel_flag = threading.Event()
        self._start_time: float = 0
        self._processed: int = 0

    def start(self, total: int) -> None:
        self._start_time = time.time()
        self._processed = 0
        self._total = total
        self._cancel_flag.clear()
        self._pause_event.set()
        self._set_state(PipelineState.RUNNING)

    def pause(self) -> None:
        self._pause_event.clear()
        self._set_state(PipelineState.PAUSED)

    def resume(self) -> None:
        self._pause_event.set()
        self._set_state(PipelineState.RUNNING)

    def cancel(self) -> None:
        self._cancel_flag.set()
        self._pause_event.set()
        self._set_state(PipelineState.CANCELLED)

    def complete(self) -> None:
        self._set_state(PipelineState.COMPLETED)

    def error(self) -> None:
        self._set_state(PipelineState.ERROR)

    def wait_if_paused(self) -> None:
        self._pause_event.wait()
        if self._cancel_flag.is_set():
            raise CancelledError("Translation cancelled by user")

    def check_cancelled(self) -> None:
        if self._cancel_flag.is_set():
            raise CancelledError("Translation cancelled by user")

    def update(self, current: int, mod_name: str = "") -> None:
        self._processed = current
        elapsed = time.time() - self._start_time
        eta = 0.0
        if current > 0:
            rate = elapsed / current
            remaining = self._total - current
            eta = rate * remaining

        self.event_bus.publish_threadsafe(
            "progress",
            ProgressEvent(
                current=current,
                total=self._total,
                mod_name=mod_name,
                eta_seconds=eta,
            ),
        )

    def _set_state(self, new_state: PipelineState) -> None:
        self.state = new_state
        self.event_bus.publish_threadsafe(
            "state_changed", StateEvent(new_state.value)
        )
