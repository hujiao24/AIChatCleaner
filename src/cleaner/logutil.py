from __future__ import annotations

from collections.abc import Callable

LogFn = Callable[[str], None]


def emit_log(log: LogFn | None, message: str) -> None:
    if log is not None:
        log(message)
