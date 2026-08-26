from cleaner.targets.base import ChatTarget, ScanItem
from cleaner.targets.cursor import CursorTarget
from cleaner.targets.vscode_copilot import VSCodeCopilotTarget
from cleaner.targets.vscode_codex import VSCodeCodexTarget
from cleaner.targets.wsl_copilot import WslCopilotTarget
from cleaner.targets.wsl_codex import WslCodexTarget
from cleaner.targets.wsl_cursor import WslCursorTarget

ALL_TARGETS: list[ChatTarget] = [
    CursorTarget(),
    VSCodeCopilotTarget(),
    VSCodeCodexTarget(),
]

TARGET_BY_ID = {t.target_id: t for t in ALL_TARGETS}

__all__ = [
    "ALL_TARGETS",
    "TARGET_BY_ID",
    "ChatTarget",
    "ScanItem",
    "CursorTarget",
    "VSCodeCopilotTarget",
    "VSCodeCodexTarget",
    "WslCursorTarget",
    "WslCopilotTarget",
    "WslCodexTarget",
]
