from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from cleaner.utils import CleanResult, count_items, expand, path_size, remove_glob, remove_path


@dataclass
class ScanItem:
    path: Path
    description: str
    exists: bool
    file_count: int
    dir_count: int
    size_bytes: int


class ChatTarget(ABC):
    target_id: str
    label: str
    description: str
    app_hint: str

    @abstractmethod
    def locations(self) -> list[tuple[Path, str]]:
        """Return (path, description) pairs to clean."""

    def scan(self, log=None) -> list[ScanItem]:
        items: list[ScanItem] = []
        for raw_path, desc in self.locations():
            path = expand(raw_path)
            exists = path.exists()
            if not exists:
                items.append(ScanItem(path, desc, False, 0, 0, 0))
                continue
            if path.is_file():
                items.append(ScanItem(path, desc, True, 1, 0, path.stat().st_size))
            else:
                files, dirs = count_items(path)
                items.append(
                    ScanItem(path, desc, True, files, dirs, path_size(path))
                )
        return items

    def clean(self, dry_run: bool = True, log=None) -> CleanResult:
        result = CleanResult(self.target_id, self.label)
        for raw_path, desc in self.locations():
            path = expand(raw_path)
            if not path.exists():
                result.skipped.append(f"{desc}: not found ({path})")
                continue
            try:
                if path.is_file() or not any(path.iterdir()) if path.is_dir() else False:
                    # single file, or empty dir
                    if path.is_dir() and not any(path.iterdir()):
                        if not dry_run:
                            path.rmdir()
                        result.deleted_dirs += 1
                    else:
                        f, d, b = remove_path(path, dry_run)
                        result.deleted_files += f
                        result.deleted_dirs += d
                        result.freed_bytes += b
                elif path.is_dir():
                    # clean contents but keep directory (e.g. sessions root)
                    for child in list(path.iterdir()):
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


class PatternTarget(ChatTarget):
    """Target that removes files matching glob patterns under a root."""

    root: Path
    patterns: list[tuple[str, str]]

    def locations(self) -> list[tuple[Path, str]]:
        return [(self.root, desc) for _, desc in self.patterns]

    def clean(self, dry_run: bool = True, log=None) -> CleanResult:
        result = CleanResult(self.target_id, self.label)
        root = expand(self.root)
        if not root.exists():
            result.skipped.append(f"root not found: {root}")
            return result
        for pattern, desc in self.patterns:
            try:
                f, d, b = remove_glob(root, pattern, dry_run)
                result.deleted_files += f
                result.deleted_dirs += d
                result.freed_bytes += b
                if f == 0 and d == 0:
                    result.skipped.append(f"{desc}: nothing to remove")
            except OSError as exc:
                result.errors.append(f"{desc} ({root / pattern}): {exc}")
        return result
