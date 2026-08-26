from __future__ import annotations

from dataclasses import dataclass, field

from cleaner.targets import (
    ChatTarget,
    CursorTarget,
    VSCodeCodexTarget,
    VSCodeCopilotTarget,
    WslCodexTarget,
    WslCopilotTarget,
    WslCursorTarget,
)
from cleaner.logutil import LogFn, emit_log
from cleaner.wsl import list_wsl_distros


@dataclass
class TargetGroup:
    platform: str
    label: str
    targets: list[ChatTarget] = field(default_factory=list)


@dataclass
class ScanSummary:
    target: ChatTarget
    items: list
    total_files: int
    total_dirs: int
    total_bytes: int


def build_target_groups(wsl_distro: str | None = None) -> list[TargetGroup]:
    groups = [
        TargetGroup(
            platform="windows",
            label="Windows 本地",
            targets=[
                CursorTarget(),
                VSCodeCopilotTarget(),
                VSCodeCodexTarget(),
            ],
        )
    ]

    distro = wsl_distro or (list_wsl_distros()[0] if list_wsl_distros() else None)
    if distro:
        groups.append(
            TargetGroup(
                platform="wsl",
                label=f"WSL ({distro})",
                targets=[
                    WslCursorTarget(distro),
                    WslCopilotTarget(distro),
                    WslCodexTarget(distro),
                ],
            )
        )
    return groups


def all_targets(wsl_distro: str | None = None) -> list[ChatTarget]:
    return [t for g in build_target_groups(wsl_distro) for t in g.targets]


def target_by_id(target_id: str, wsl_distro: str | None = None) -> ChatTarget | None:
    for target in all_targets(wsl_distro):
        if target.target_id == target_id:
            return target
    return None


def scan_targets(
    targets: list[ChatTarget],
    log: LogFn | None = None,
) -> list[ScanSummary]:
    summaries: list[ScanSummary] = []
    total = len(targets)
    for index, target in enumerate(targets, 1):
        emit_log(log, f"── [{index}/{total}] {target.label} ──")
        items = target.scan(log=log)
        summary = ScanSummary(
            target=target,
            items=items,
            total_files=sum(i.file_count for i in items if i.exists),
            total_dirs=sum(i.dir_count for i in items if i.exists),
            total_bytes=sum(i.size_bytes for i in items if i.exists),
        )
        summaries.append(summary)
        from cleaner.utils import format_bytes

        emit_log(
            log,
            f"  小计: 文件 {summary.total_files}, 目录 {summary.total_dirs}, "
            f"大小 {format_bytes(summary.total_bytes)}",
        )
    return summaries


def clean_targets(
    targets: list[ChatTarget],
    dry_run: bool = False,
    log: LogFn | None = None,
) -> list[CleanResult]:
    results: list[CleanResult] = []
    total = len(targets)
    for index, target in enumerate(targets, 1):
        emit_log(log, f"── [{index}/{total}] {target.label} ──")
        result = target.clean(dry_run=dry_run, log=log)
        results.append(result)
        from cleaner.utils import format_bytes

        emit_log(
            log,
            f"  结果: 删除文件 {result.deleted_files}, 目录 {result.deleted_dirs}, "
            f"释放 {format_bytes(result.freed_bytes)}",
        )
    return results
