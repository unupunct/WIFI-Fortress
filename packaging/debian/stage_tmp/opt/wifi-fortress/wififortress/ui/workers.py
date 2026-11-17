"""Background worker plumbing.

Long-running service calls never run on the GUI thread.  A :class:`Worker`
wraps a callable in a QThread and emits ``progress`` / ``finished`` /
``failed`` signals.  Cancellation is cooperative through a
:class:`~wififortress.core.process.CancelToken` that the service checks.
"""

from __future__ import annotations

import inspect
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal

from wififortress.core.logging import get_logger
from wififortress.core.process import CancelToken, CancelledError

log = get_logger(__name__)


class Worker(QObject):
    progress = Signal(str, int)          # message, percent (-1 = indeterminate)
    finished = Signal(object)            # result
    failed = Signal(str, str)            # message, traceback
    cancelled = Signal()

    def __init__(
        self,
        fn: Callable[..., Any],
        *args: Any,
        token: CancelToken | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self.token = token or CancelToken()
        self._thread: QThread | None = None

    def move_to_thread(self) -> QThread:
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self.run)
        return self._thread

    def run(self) -> None:
        try:
            kwargs = dict(self._kwargs)
            if "token" not in kwargs:
                try:
                    accepts_token = "token" in inspect.signature(self._fn).parameters
                except (TypeError, ValueError):  # builtins without signature
                    accepts_token = False
                if accepts_token:
                    kwargs["token"] = self.token
            result = self._fn(*self._args, **kwargs)
            if self.token.cancelled:
                self.cancelled.emit()
                return
            self.finished.emit(result)
        except CancelledError:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001 - reported to the UI
            detail = traceback.format_exc()
            log.error("Worker failed: %s", exc)
            self.failed.emit(str(exc) or exc.__class__.__name__, detail)
        finally:
            if self._thread:
                self._thread.quit()

    def request_cancel(self) -> None:
        self.token.cancel()

    def emit_progress(self, message: str, percent: int = -1) -> None:
        self.progress.emit(message, percent)


class WorkerController(QObject):
    """Owns a worker + thread and keeps them alive for the UI."""

    progress = Signal(str, int)
    finished = Signal(object)
    failed = Signal(str, str)
    cancelled = Signal()
    started = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._worker: Worker | None = None
        self._thread: QThread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def start(
        self,
        fn: Callable[..., Any],
        *args: Any,
        progress_cb: Callable[[str, int], None] | None = None,
        **kwargs: Any,
    ) -> None:
        if self.running:
            raise RuntimeError("A task is already running")
        if progress_cb is not None:
            try:
                if "progress_cb" in inspect.signature(fn).parameters:
                    kwargs.setdefault("progress_cb", progress_cb)
            except (TypeError, ValueError):
                pass
        worker = Worker(fn, *args, **kwargs)
        thread = worker.move_to_thread()
        self._worker = worker
        self._thread = thread
        worker.progress.connect(self.progress)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        worker.cancelled.connect(self._on_cancelled)
        thread.start()
        self.started.emit()

    def cancel(self) -> None:
        if self._worker:
            self._worker.request_cancel()

    def wait(self, ms: int = 5000) -> bool:
        if self._thread:
            return self._thread.wait(ms)
        return True

    def _cleanup(self) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait(3000)
        self._worker = None
        self._thread = None

    def _on_finished(self, result: object) -> None:
        self._cleanup()
        self.finished.emit(result)

    def _on_failed(self, message: str, detail: str) -> None:
        self._cleanup()
        self.failed.emit(message, detail)

    def _on_cancelled(self) -> None:
        self._cleanup()
        self.cancelled.emit()
