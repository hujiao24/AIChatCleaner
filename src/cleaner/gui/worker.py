from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Qt, Signal

from cleaner.logutil import LogFn
from cleaner.service import ScanSummary, clean_targets, scan_targets
from cleaner.targets.base import ChatTarget


class Worker(QObject):
    progress = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def _log(self, message: str) -> None:
        self.progress.emit(message)

    def run(self):
        self.progress.emit("▶ 后台任务已启动，正在处理…")
        try:
            result = self._fn(*self._args, log=self._log, **self._kwargs)
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001 - surface to UI
            self.failed.emit(str(exc))


def run_in_thread(
    parent,
    fn,
    on_finished,
    on_failed,
    on_progress=None,
    *args,
    **kwargs,
) -> tuple[QThread, Worker]:
    thread = QThread(parent)
    worker = Worker(fn, *args, **kwargs)
    worker.moveToThread(thread)

    thread.started.connect(worker.run)
    worker.finished.connect(on_finished)
    worker.failed.connect(on_failed)
    if on_progress is not None:
        worker.progress.connect(on_progress, Qt.ConnectionType.QueuedConnection)

    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    worker.failed.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)

    # 防止 Python 回收 worker，导致跨线程信号失效
    thread._worker_ref = worker
    thread.start()
    return thread, worker


def do_scan(targets: list[ChatTarget], log: LogFn | None = None) -> list[ScanSummary]:
    return scan_targets(targets, log=log)


def do_clean(
    targets: list[ChatTarget],
    dry_run: bool,
    log: LogFn | None = None,
):
    return clean_targets(targets, dry_run=dry_run, log=log)
