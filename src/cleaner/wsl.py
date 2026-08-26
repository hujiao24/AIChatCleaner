from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from cleaner.logutil import LogFn, emit_log
from cleaner.utils import run_hidden


@dataclass
class WslTreeStats:
    files: int
    dirs: int
    bytes: int
    exists: bool


class WslExecutor:
    def __init__(self, distro: str):
        self.distro = distro

    @property
    def display_prefix(self) -> str:
        return f"WSL:{self.distro}"

    def display_path(self, linux_path: str) -> Path:
        normalized = (
            linux_path.replace("~", "/root")
            if linux_path.startswith("~")
            else linux_path
        )
        return Path(f"wsl://{self.distro}{normalized}")

    def run(
        self,
        script: str,
        timeout: int = 180,
        log: LogFn | None = None,
        description: str | None = None,
    ) -> tuple[int, str, str]:
        if log and description:
            emit_log(log, f"       [WSL] {description}")
        cmd = ["wsl", "-d", self.distro, "-e", "bash", "-lc", script]
        proc = run_hidden(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        if proc.returncode != 0 and log:
            err = proc.stderr.strip()
            if err:
                emit_log(log, f"       [WSL 警告] {err[:200]}")
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()

    def path_exists(self, linux_path: str) -> bool:
        script = rf"""
p={linux_path}
if [ -e "$p" ]; then echo yes; else echo no; fi
"""
        _, stdout, _ = self.run(script, timeout=30)
        return stdout.strip() == "yes"

    def list_agent_transcript_dirs(self) -> list[str]:
        script = r"""
for d in ~/.cursor/projects/*/agent-transcripts; do
  [ -d "$d" ] && echo "$d"
done
"""
        _, stdout, _ = self.run(script, timeout=120)
        return [line.strip() for line in stdout.splitlines() if line.strip()]

    def scan_path(
        self,
        linux_path: str,
        log: LogFn | None = None,
        description: str | None = None,
        quiet: bool = False,
    ) -> WslTreeStats:
        if log and description and not quiet:
            emit_log(log, f"       [WSL] 统计: {linux_path}")
        script = rf"""
p={linux_path}
if [ ! -e "$p" ]; then
  echo "0 0 0 missing"
  exit 0
fi
if [ -f "$p" ]; then
  echo "1 0 $(stat -c%s "$p") ok"
  exit 0
fi
files=$(find "$p" -type f 2>/dev/null | wc -l)
dirs=$(find "$p" -type d 2>/dev/null | wc -l)
bytes=$(du -sb "$p" 2>/dev/null | cut -f1)
echo "$files $dirs ${{bytes:-0}} ok"
"""
        _, stdout, stderr = self.run(script, log=log if not quiet else None)
        if stderr and "ok" not in stdout:
            return WslTreeStats(0, 0, 0, False)
        parts = stdout.split()
        if len(parts) < 4 or parts[-1] == "missing":
            return WslTreeStats(0, 0, 0, False)
        return WslTreeStats(int(parts[0]), int(parts[1]), int(parts[2]), True)

    def clean_file(
        self,
        linux_path: str,
        dry_run: bool,
        log: LogFn | None = None,
    ) -> tuple[int, int, int]:
        stats = self.scan_path(linux_path, log=log, quiet=True)
        if not stats.exists:
            return 0, 0, 0
        if dry_run:
            emit_log(log, f"       [模拟] 将删除文件 ({format_bytes(stats.bytes)})")
            return stats.files, stats.dirs, stats.bytes
        script = rf"""
p={linux_path}
if [ -f "$p" ]; then rm -f "$p"; fi
"""
        self.run(script, log=log, description=f"删除 {linux_path}")
        return stats.files, stats.dirs, stats.bytes

    def clean_dir_contents(
        self,
        linux_path: str,
        dry_run: bool,
        log: LogFn | None = None,
    ) -> tuple[int, int, int]:
        stats = self.scan_path(linux_path, log=log, quiet=True)
        if not stats.exists:
            return 0, 0, 0
        if dry_run:
            emit_log(
                log,
                f"       [模拟] 将清空目录 ({stats.files} 文件, {format_bytes(stats.bytes)})",
            )
            return stats.files, stats.dirs, stats.bytes
        script = rf"""
p={linux_path}
if [ -d "$p" ]; then
  find "$p" -mindepth 1 -delete 2>/dev/null
fi
"""
        self.run(script, log=log, description=f"清空 {linux_path}")
        return stats.files, stats.dirs, stats.bytes

    def clean_agent_transcripts(
        self,
        dry_run: bool,
        log: LogFn | None = None,
    ) -> tuple[int, int, int]:
        dirs = self.list_agent_transcript_dirs()
        if not dirs:
            return 0, 0, 0

        if dry_run:
            total_files = total_dirs = total_bytes = 0
            for linux_path in dirs:
                stats = self.scan_path(linux_path, quiet=True)
                total_files += stats.files
                total_dirs += stats.dirs
                total_bytes += stats.bytes
            emit_log(
                log,
                f"       [模拟] 将清理 {len(dirs)} 个目录, "
                f"{total_files} 文件, {format_bytes(total_bytes)}",
            )
            return total_files, total_dirs, total_bytes

        script = r"""
total_files=0
total_dirs=0
total_bytes=0
for d in ~/.cursor/projects/*/agent-transcripts; do
  [ -d "$d" ] || continue
  fc=$(find "$d" -type f 2>/dev/null | wc -l)
  dc=$(find "$d" -type d 2>/dev/null | wc -l)
  bc=$(du -sb "$d" 2>/dev/null | cut -f1)
  total_files=$((total_files + fc))
  total_dirs=$((total_dirs + dc))
  total_bytes=$((total_bytes + ${bc:-0}))
  find "$d" -mindepth 1 -delete 2>/dev/null
done
echo "$total_files $total_dirs $total_bytes"
"""
        _, stdout, _ = self.run(
            script,
            log=log,
            description="批量清理 agent-transcripts",
        )
        parts = stdout.split()
        if len(parts) >= 3:
            return int(parts[0]), int(parts[1]), int(parts[2])
        return 0, 0, 0


def format_bytes(num: int) -> str:
    from cleaner.utils import format_bytes as fmt

    return fmt(num)


def list_wsl_distros() -> list[str]:
    if sys.platform != "win32":
        return []
    try:
        proc = run_hidden(
            ["wsl", "-l", "-q"],
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return []

    raw = proc.stdout
    if raw.startswith(b"\xff\xfe") or (len(raw) >= 2 and raw[1:2] == b"\x00"):
        text = raw.decode("utf-16-le")
    else:
        text = raw.decode("utf-8", errors="replace")

    distros: list[str] = []
    for line in text.splitlines():
        name = line.replace("\x00", "").strip()
        if name:
            distros.append(name)
    return distros


def wsl_available() -> bool:
    return bool(list_wsl_distros())
