from __future__ import annotations

from cleaner.logutil import emit_log
from cleaner.targets.base import ChatTarget, ScanItem
from cleaner.utils import CleanResult, format_bytes
from cleaner.wsl import WslExecutor


class WslCursorTarget(ChatTarget):
    target_id = "cursor-wsl"
    description = "WSL 中 Cursor Agent 本地对话 (agent-transcripts)"
    app_hint = "请先关闭 WSL 内的 Cursor / Remote 会话后再清理。"

    def __init__(self, distro: str):
        self.distro = distro
        self.executor = WslExecutor(distro)
        self.label = f"Cursor (WSL: {distro})"

    def locations(self) -> list[tuple[str, str]]:
        return [
            ("~/.cursor/projects", "各项目 agent-transcripts 汇总"),
        ]

    def scan(self, log=None) -> list[ScanItem]:
        emit_log(log, f"  连接 WSL 发行版: {self.distro}")
        emit_log(log, "  枚举 ~/.cursor/projects/*/agent-transcripts …")
        dirs = self.executor.list_agent_transcript_dirs()
        emit_log(log, f"  发现 {len(dirs)} 个 agent-transcripts 目录")

        total_files = total_dirs = total_bytes = 0
        for index, linux_path in enumerate(dirs, 1):
            emit_log(log, f"  [{index}/{len(dirs)}] 扫描: {linux_path}")
            stats = self.executor.scan_path(linux_path, log=log, quiet=True)
            total_files += stats.files
            total_dirs += stats.dirs
            total_bytes += stats.bytes
            emit_log(
                log,
                f"       → {stats.files} 文件, {stats.dirs} 目录, {format_bytes(stats.bytes)}",
            )

        exists = bool(dirs) or self.executor.path_exists("~/.cursor/projects")
        return [
            ScanItem(
                self.executor.display_path("~/.cursor/projects"),
                "各项目 agent-transcripts 汇总",
                exists,
                total_files,
                total_dirs,
                total_bytes,
            )
        ]

    def clean(self, dry_run: bool = True, log=None) -> CleanResult:
        result = CleanResult(self.target_id, self.label)
        emit_log(log, f"  连接 WSL 发行版: {self.distro}")
        try:
            dirs = self.executor.list_agent_transcript_dirs()
            emit_log(log, f"  清理 {len(dirs)} 个 agent-transcripts 目录")
            for linux_path in dirs:
                emit_log(log, f"    删除: {linux_path}")
            f, d, b = self.executor.clean_agent_transcripts(dry_run, log=log)
            result.deleted_files = f
            result.deleted_dirs = d
            result.freed_bytes = b
            if f == 0 and d == 0 and b == 0:
                result.skipped.append("WSL Cursor agent-transcripts: 无数据或未找到")
        except OSError as exc:
            result.errors.append(str(exc))
        return result
