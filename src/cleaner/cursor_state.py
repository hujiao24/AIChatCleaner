from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from cleaner.logutil import LogFn, emit_log
from cleaner.utils import format_bytes, path_size


@dataclass
class VscdbCleanStats:
    db_path: Path
    deleted_rows: int = 0
    freed_bytes: int = 0
    details: list[str] = field(default_factory=list)


ITEMTABLE_CHAT_KEYS = (
    "composer.composerData",
    "workbench.backgroundComposer.workspacePersistentData",
    "workbench.backgroundComposer.persistentData",
    "workbench.panel.aichat.view.aichat.chatdata",
    "aiService.prompts",
    "aiService.generations",
)

ITEMTABLE_CHAT_PREFIXES = (
    "workbench.panel.composerChatViewPane.",
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _db_size(path: Path) -> int:
    total = path_size(path)
    for suffix in ("-wal", "-shm"):
        p = Path(str(path) + suffix)
        if p.exists():
            total += p.stat().st_size
    return total


def scan_vscdb_chat(db_path: Path) -> tuple[int, int]:
    if not db_path.exists():
        return 0, 0
    rows = 0
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        if _table_exists(conn, "composerHeaders"):
            rows += conn.execute("SELECT COUNT(*) FROM composerHeaders").fetchone()[0]
        if _table_exists(conn, "cursorDiskKV"):
            rows += conn.execute(
                """
                SELECT COUNT(*) FROM cursorDiskKV
                WHERE key LIKE 'composerData:%'
                   OR key LIKE 'bubbleId:%'
                   OR key LIKE 'checkpointId:%'
                """
            ).fetchone()[0]
        if _table_exists(conn, "ItemTable"):
            exact = ",".join("?" for _ in ITEMTABLE_CHAT_KEYS)
            rows += conn.execute(
                f"SELECT COUNT(*) FROM ItemTable WHERE key IN ({exact})",
                ITEMTABLE_CHAT_KEYS,
            ).fetchone()[0]
            for prefix in ITEMTABLE_CHAT_PREFIXES:
                rows += conn.execute(
                    "SELECT COUNT(*) FROM ItemTable WHERE key LIKE ?",
                    (f"{prefix}%",),
                ).fetchone()[0]
        conn.close()
    except sqlite3.Error:
        return 0, 0
    return rows, _db_size(db_path)


def clean_vscdb_chat(
    db_path: Path,
    dry_run: bool = True,
    log: LogFn | None = None,
) -> VscdbCleanStats:
    stats = VscdbCleanStats(db_path=db_path)
    if not db_path.exists():
        return stats

    before = _db_size(db_path)
    emit_log(log, f"  处理数据库: {db_path}")

    if dry_run:
        rows, _ = scan_vscdb_chat(db_path)
        stats.deleted_rows = rows
        stats.freed_bytes = before
        emit_log(log, f"       [模拟] 将清除约 {rows} 条对话记录, 数据库 {format_bytes(before)}")
        return stats

    try:
        conn = sqlite3.connect(db_path)
        if _table_exists(conn, "composerHeaders"):
            n = conn.execute("SELECT COUNT(*) FROM composerHeaders").fetchone()[0]
            if n:
                conn.execute("DELETE FROM composerHeaders")
                stats.deleted_rows += n
                emit_log(log, f"       清除 composerHeaders: {n} 条（侧边栏会话列表）")

        if _table_exists(conn, "cursorDiskKV"):
            for pattern in ("composerData:%", "bubbleId:%", "checkpointId:%"):
                n = conn.execute(
                    "SELECT COUNT(*) FROM cursorDiskKV WHERE key LIKE ?",
                    (pattern,),
                ).fetchone()[0]
                if n:
                    conn.execute(
                        "DELETE FROM cursorDiskKV WHERE key LIKE ?",
                        (pattern,),
                    )
                    stats.deleted_rows += n
                    emit_log(log, f"       清除 cursorDiskKV {pattern}: {n} 条（对话内容）")

        if _table_exists(conn, "ItemTable"):
            exact = ",".join("?" for _ in ITEMTABLE_CHAT_KEYS)
            n = conn.execute(
                f"SELECT COUNT(*) FROM ItemTable WHERE key IN ({exact})",
                ITEMTABLE_CHAT_KEYS,
            ).fetchone()[0]
            if n:
                conn.execute(
                    f"DELETE FROM ItemTable WHERE key IN ({exact})",
                    ITEMTABLE_CHAT_KEYS,
                )
                stats.deleted_rows += n
                emit_log(log, f"       清除 ItemTable 会话键: {n} 条")

            for prefix in ITEMTABLE_CHAT_PREFIXES:
                n = conn.execute(
                    "SELECT COUNT(*) FROM ItemTable WHERE key LIKE ?",
                    (f"{prefix}%",),
                ).fetchone()[0]
                if n:
                    conn.execute(
                        "DELETE FROM ItemTable WHERE key LIKE ?",
                        (f"{prefix}%",),
                    )
                    stats.deleted_rows += n
                    emit_log(log, f"       清除 ItemTable {prefix}*: {n} 条")

        conn.commit()
        conn.execute("VACUUM")
        conn.close()

        for suffix in ("-wal", "-shm"):
            wal = Path(str(db_path) + suffix)
            if wal.exists():
                wal.unlink(missing_ok=True)

        after = _db_size(db_path)
        stats.freed_bytes = max(before - after, 0)
        emit_log(
            log,
            f"       完成, 删除 {stats.deleted_rows} 条, 释放约 {format_bytes(stats.freed_bytes)}",
        )
    except sqlite3.Error as exc:
        emit_log(log, f"       错误: {exc}")

    return stats


def cursor_user_root() -> Path:
    import os

    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return appdata / "Cursor" / "User"


def iter_cursor_vscdb_files() -> list[tuple[Path, str]]:
    root = cursor_user_root()
    files: list[tuple[Path, str]] = []

    global_db = root / "globalStorage" / "state.vscdb"
    if global_db.exists():
        files.append((global_db, "全局对话数据库（侧边栏 + 消息内容）"))

    ws_root = root / "workspaceStorage"
    if ws_root.exists():
        for entry in sorted(ws_root.iterdir()):
            if not entry.is_dir():
                continue
            db = entry / "state.vscdb"
            if db.exists():
                files.append((db, f"工作区会话索引 ({entry.name[:8]}…)"))

    return files


def scan_all_cursor_vscdb(log: LogFn | None = None) -> tuple[int, int, int]:
    total_rows = total_bytes = 0
    file_count = 0
    for db_path, desc in iter_cursor_vscdb_files():
        emit_log(log, f"  检查: {db_path}")
        rows, size = scan_vscdb_chat(db_path)
        if rows:
            emit_log(log, f"       → {desc}: {rows} 条记录, {format_bytes(size)}")
        else:
            emit_log(log, "       → 无对话记录")
        total_rows += rows
        total_bytes += size
        file_count += 1
    return file_count, total_rows, total_bytes


def clean_all_cursor_vscdb(dry_run: bool = True, log: LogFn | None = None) -> tuple[int, int]:
    deleted_rows = freed_bytes = 0
    emit_log(log, "  清理 Cursor 侧边栏/Composer 对话 (state.vscdb)…")
    for db_path, desc in iter_cursor_vscdb_files():
        emit_log(log, f"  [{desc}]")
        result = clean_vscdb_chat(db_path, dry_run=dry_run, log=log)
        deleted_rows += result.deleted_rows
        freed_bytes += result.freed_bytes
    return deleted_rows, freed_bytes
