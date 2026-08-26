from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


def run_hidden(*popenargs, **kwargs):
    """Windows 下静默运行子进程，避免 GUI 程序弹出黑色终端窗口。"""
    if sys.platform == "win32":
        flags = kwargs.pop("creationflags", 0)
        kwargs["creationflags"] = flags | subprocess.CREATE_NO_WINDOW
    return subprocess.run(*popenargs, **kwargs)


@dataclass
class CleanResult:
    target_id: str
    label: str
    deleted_files: int = 0
    deleted_dirs: int = 0
    freed_bytes: int = 0
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                pass
    return total


def count_items(path: Path) -> tuple[int, int]:
    """Return (file_count, dir_count) under path, excluding path itself."""
    if not path.exists():
        return 0, 0
    if path.is_file():
        return 1, 0
    files = dirs = 0
    for child in path.rglob("*"):
        if child.is_file():
            files += 1
        elif child.is_dir():
            dirs += 1
    return files, dirs


def expand(path: Path) -> Path:
    return Path(os.path.expandvars(str(path))).expanduser()


def remove_path(path: Path, dry_run: bool) -> tuple[int, int, int]:
    """Remove file or directory tree. Returns (files, dirs, bytes)."""
    if not path.exists():
        return 0, 0, 0

    size = path_size(path)
    if path.is_file():
        if not dry_run:
            path.unlink(missing_ok=True)
        return 1, 0, size

    files, dirs = count_items(path)
    dirs += 1  # include root
    if not dry_run:
        shutil.rmtree(path, ignore_errors=False)
    return files, dirs, size


def remove_glob(root: Path, pattern: str, dry_run: bool) -> tuple[int, int, int]:
    if not root.exists():
        return 0, 0, 0
    total_files = total_dirs = total_bytes = 0
    for match in root.glob(pattern):
        f, d, b = remove_path(match, dry_run)
        total_files += f
        total_dirs += d
        total_bytes += b
    return total_files, total_dirs, total_bytes


def format_bytes(num: int) -> str:
    units = ("B", "KB", "MB", "GB")
    value = float(num)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{num} B"
