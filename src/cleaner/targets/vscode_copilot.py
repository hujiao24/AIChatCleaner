from __future__ import annotations

import os
from pathlib import Path

from cleaner.logutil import emit_log
from cleaner.targets.base import ChatTarget, ScanItem
from cleaner.utils import CleanResult, expand, format_bytes, remove_path


class VSCodeCopilotTarget(ChatTarget):
    target_id = "copilot"
    label = "VS Code Copilot Chat"
    description = "VS Code 中 GitHub Copilot Chat 的本地会话"
    app_hint = "请先关闭 VS Code 后再清理。"

    def locations(self) -> list[tuple[Path, str]]:
        appdata = Path(
            os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
        )
        gs = appdata / "Code" / "User" / "globalStorage"
        return [
            (
                gs / "github.copilot-chat" / "session-store.db",
                "Copilot Chat 会话数据库",
            ),
            (
                gs / "github.copilot-chat" / "session-store.db-wal",
                "Copilot Chat 会话 WAL",
            ),
            (
                gs / "github.copilot-chat" / "session-store.db-shm",
                "Copilot Chat 会话 SHM",
            ),
            (
                gs / "emptyWindowChatSessions",
                "无工作区窗口的 Copilot 会话 (jsonl)",
            ),
        ]

    def clean(self, dry_run: bool = True, log=None):
        result = CleanResult(self.target_id, self.label)
        for raw_path, desc in self.locations():
            path = expand(raw_path)
            if not path.exists():
                result.skipped.append(f"{desc}: not found")
                emit_log(log, f"  跳过: 不存在 {path}")
                continue
            emit_log(log, f"  清理: {path}")
            try:
                if path.is_dir():
                    children = list(path.iterdir())
                    emit_log(log, f"       共 {len(children)} 个条目")
                    for child in children:
                        if child.suffix == ".jsonl" or child.is_dir():
                            emit_log(log, f"       删除: {child.name}")
                            f, d, b = remove_path(child, dry_run)
                            result.deleted_files += f
                            result.deleted_dirs += d
                            result.freed_bytes += b
                else:
                    f, d, b = remove_path(path, dry_run)
                    result.deleted_files += f
                    result.deleted_dirs += d
                    result.freed_bytes += b
            except OSError as exc:
                result.errors.append(f"{desc} ({path}): {exc}")
        return result

    def scan(self, log=None):
        items: list[ScanItem] = []
        for raw_path, desc in self.locations():
            path = expand(raw_path)
            emit_log(log, f"  检查: {path}")
            if not path.exists():
                emit_log(log, "       → 不存在")
                items.append(ScanItem(path, desc, False, 0, 0, 0))
                continue
            if path.is_dir():
                jsonl_files = list(path.glob("*.jsonl"))
                size = sum(p.stat().st_size for p in jsonl_files)
                emit_log(
                    log,
                    f"       → 目录, {len(jsonl_files)} 个 jsonl, {format_bytes(size)}",
                )
                for jf in jsonl_files[:5]:
                    emit_log(log, f"         · {jf.name} ({format_bytes(jf.stat().st_size)})")
                if len(jsonl_files) > 5:
                    emit_log(log, f"         · … 另有 {len(jsonl_files) - 5} 个文件")
                items.append(
                    ScanItem(path, desc, True, len(jsonl_files), 0, size)
                )
            else:
                size = path.stat().st_size
                emit_log(log, f"       → 文件, {format_bytes(size)}")
                items.append(ScanItem(path, desc, True, 1, 0, size))
        return items
