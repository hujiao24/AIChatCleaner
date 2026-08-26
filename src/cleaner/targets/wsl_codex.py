from __future__ import annotations

import os

from cleaner.logutil import emit_log
from cleaner.targets.base import ChatTarget, ScanItem
from cleaner.utils import CleanResult, format_bytes
from cleaner.wsl import WslExecutor


class WslCodexTarget(ChatTarget):
    target_id = "codex-wsl"
    description = "WSL 中 OpenAI Codex 扩展的本地会话"
    app_hint = "请先关闭 WSL 内的 VS Code / Codex。可通过 CODEX_HOME 自定义路径。"

    def __init__(self, distro: str):
        self.distro = distro
        self.executor = WslExecutor(distro)
        self.label = f"Codex (WSL: {distro})"

    def _codex_home_expr(self) -> str:
        if os.environ.get("CODEX_HOME"):
            return os.environ["CODEX_HOME"].replace("\\", "/")
        return "${CODEX_HOME:-$HOME/.codex}"

    def _codex_home_display(self) -> str:
        if os.environ.get("CODEX_HOME"):
            return os.environ["CODEX_HOME"].replace("\\", "/")
        return "~/.codex"

    def locations(self) -> list[tuple[str, str]]:
        base = self._codex_home_expr()
        return [
            (f"{base}/sessions", "Codex 活跃会话目录"),
            (f"{base}/archived_sessions", "Codex 归档会话目录"),
        ]

    def scan(self, log=None) -> list[ScanItem]:
        emit_log(log, f"  连接 WSL 发行版: {self.distro}")
        codex_home_display = self._codex_home_display()
        emit_log(log, f"  Codex 目录: {codex_home_display}")
        items: list[ScanItem] = []
        for suffix, desc in (
            ("/sessions", "Codex 活跃会话目录"),
            ("/archived_sessions", "Codex 归档会话目录"),
        ):
            linux_path = f"{self._codex_home_expr()}{suffix}"
            display = self.executor.display_path(f"{codex_home_display}{suffix}")
            emit_log(log, f"  扫描: {display}")
            stats = self.executor.scan_path(
                linux_path,
                log=log,
                description=desc,
            )
            if stats.exists:
                emit_log(
                    log,
                    f"       → {stats.files} 文件, {stats.dirs} 目录, {format_bytes(stats.bytes)}",
                )
            else:
                emit_log(log, "       → 不存在")
            items.append(
                ScanItem(
                    display,
                    desc,
                    stats.exists,
                    stats.files,
                    stats.dirs,
                    stats.bytes,
                )
            )
        return items

    def clean(self, dry_run: bool = True, log=None) -> CleanResult:
        result = CleanResult(self.target_id, self.label)
        emit_log(log, f"  连接 WSL 发行版: {self.distro}")
        for suffix, desc in (
            ("/sessions", "Codex 活跃会话目录"),
            ("/archived_sessions", "Codex 归档会话目录"),
        ):
            linux_path = f"{self._codex_home_expr()}{suffix}"
            display = self.executor.display_path(f"{self._codex_home_display()}{suffix}")
            emit_log(log, f"  清理: {display}")
            try:
                f, d, b = self.executor.clean_dir_contents(linux_path, dry_run, log=log)
                result.deleted_files += f
                result.deleted_dirs += d
                result.freed_bytes += b
                if f == 0 and d == 0 and b == 0:
                    result.skipped.append(f"{desc}: not found")
                    emit_log(log, "       → 不存在，已跳过")
            except OSError as exc:
                result.errors.append(f"{desc}: {exc}")
        return result
