from __future__ import annotations

import os
from pathlib import Path

from cleaner.logutil import emit_log
from cleaner.targets.base import ChatTarget, ScanItem
from cleaner.utils import CleanResult, format_bytes, path_size, remove_path


def codex_home() -> Path:
    override = os.environ.get("CODEX_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".codex"


class VSCodeCodexTarget(ChatTarget):
    target_id = "codex"
    label = "VS Code Codex"
    description = "OpenAI Codex 扩展的本地会话（rollout jsonl）"
    app_hint = "请先关闭 VS Code / Codex 后再清理。可通过 CODEX_HOME 环境变量自定义存储位置。"

    def locations(self) -> list[tuple[Path, str]]:
        base = codex_home()
        return [
            (base / "sessions", "Codex 活跃会话目录"),
            (base / "archived_sessions", "Codex 归档会话目录"),
        ]

    def clean(self, dry_run: bool = True, log=None):
        result = CleanResult(self.target_id, self.label)
        base = codex_home()
        if not base.exists():
            result.skipped.append(f"Codex 目录不存在: {base}")
            emit_log(log, f"  目录不存在: {base}")
            return result

        emit_log(log, f"  Codex 根目录: {base}")
        for folder_name in ("sessions", "archived_sessions"):
            folder = base / folder_name
            if not folder.exists():
                result.skipped.append(f"{folder_name}: not found")
                emit_log(log, f"  跳过: 不存在 {folder}")
                continue
            emit_log(log, f"  清理目录: {folder}")
            try:
                for child in list(folder.rglob("*")):
                    if child.is_file():
                        emit_log(log, f"       删除: {child.relative_to(base)}")
                        f, d, b = remove_path(child, dry_run)
                        result.deleted_files += f
                        result.deleted_dirs += d
                        result.freed_bytes += b
                if not dry_run:
                    for child in sorted(
                        folder.rglob("*"),
                        key=lambda p: len(p.parts),
                        reverse=True,
                    ):
                        if child.is_dir() and not any(child.iterdir()):
                            child.rmdir()
                            result.deleted_dirs += 1
            except OSError as exc:
                result.errors.append(f"{folder_name} ({folder}): {exc}")
        return result

    def scan(self, log=None):
        items: list[ScanItem] = []
        base = codex_home()
        emit_log(log, f"  Codex 根目录: {base}")
        if not base.exists():
            emit_log(log, "  根目录不存在")
        for raw_path, desc in self.locations():
            path = raw_path if isinstance(raw_path, Path) else Path(raw_path)
            emit_log(log, f"  扫描: {path}")
            exists = path.exists()
            if not exists:
                emit_log(log, "       → 不存在")
                items.append(ScanItem(path, desc, False, 0, 0, 0))
                continue
            files = [p for p in path.rglob("*") if p.is_file()]
            dirs = [p for p in path.rglob("*") if p.is_dir()]
            size = path_size(path)
            emit_log(
                log,
                f"       → {len(files)} 文件, {len(dirs)} 目录, {format_bytes(size)}",
            )
            for sample in files[:5]:
                emit_log(
                    log,
                    f"         · {sample.relative_to(base)} ({format_bytes(sample.stat().st_size)})",
                )
            if len(files) > 5:
                emit_log(log, f"         · … 另有 {len(files) - 5} 个文件")
            items.append(
                ScanItem(path, desc, True, len(files), len(dirs), size)
            )
        return items
