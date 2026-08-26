from __future__ import annotations

from cleaner.logutil import emit_log
from cleaner.targets.base import ChatTarget, ScanItem
from cleaner.utils import CleanResult, format_bytes
from cleaner.wsl import WslExecutor


class WslCopilotTarget(ChatTarget):
    target_id = "copilot-wsl"
    description = "WSL 中 VS Code Remote 的 GitHub Copilot Chat 会话"
    app_hint = "请先关闭 WSL Remote 的 VS Code 后再清理。"

    def __init__(self, distro: str):
        self.distro = distro
        self.executor = WslExecutor(distro)
        self.label = f"Copilot Chat (WSL: {distro})"

    def locations(self) -> list[tuple[str, str]]:
        base = "~/.vscode-server/data/User/globalStorage/github.copilot-chat"
        return [
            (f"{base}/session-store.db", "Copilot Chat 会话数据库"),
            (f"{base}/session-store.db-wal", "Copilot Chat 会话 WAL"),
            (f"{base}/session-store.db-shm", "Copilot Chat 会话 SHM"),
        ]

    def scan(self, log=None) -> list[ScanItem]:
        emit_log(log, f"  连接 WSL 发行版: {self.distro}")
        items: list[ScanItem] = []
        for linux_path, desc in self.locations():
            display = self.executor.display_path(linux_path)
            emit_log(log, f"  检查: {display}")
            stats = self.executor.scan_path(
                linux_path,
                log=log,
                description=desc,
            )
            file_count = stats.files if stats.exists else 0
            if stats.exists:
                emit_log(
                    log,
                    f"       → {file_count} 文件, {format_bytes(stats.bytes)}",
                )
            else:
                emit_log(log, "       → 不存在")
            items.append(
                ScanItem(
                    display,
                    desc,
                    stats.exists,
                    file_count,
                    0,
                    stats.bytes,
                )
            )
        return items

    def clean(self, dry_run: bool = True, log=None) -> CleanResult:
        result = CleanResult(self.target_id, self.label)
        emit_log(log, f"  连接 WSL 发行版: {self.distro}")
        for linux_path, desc in self.locations():
            display = self.executor.display_path(linux_path)
            emit_log(log, f"  清理: {display}")
            try:
                f, d, b = self.executor.clean_file(linux_path, dry_run, log=log)
                result.deleted_files += f
                result.deleted_dirs += d
                result.freed_bytes += b
                if f == 0 and not self.executor.path_exists(linux_path):
                    result.skipped.append(f"{desc}: not found")
                    emit_log(log, "       → 不存在，已跳过")
            except OSError as exc:
                result.errors.append(f"{desc}: {exc}")
        return result
