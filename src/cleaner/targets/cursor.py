from __future__ import annotations

import os
from pathlib import Path

from cleaner.cursor_state import (
    clean_all_cursor_vscdb,
    cursor_user_root,
    iter_cursor_vscdb_files,
    scan_all_cursor_vscdb,
    scan_vscdb_chat,
)
from cleaner.logutil import emit_log
from cleaner.targets.base import ChatTarget, ScanItem
from cleaner.utils import CleanResult, count_items, expand, format_bytes, path_size, remove_path


class CursorTarget(ChatTarget):
    target_id = "cursor"
    label = "Cursor"
    description = "Cursor 侧边栏对话、Composer 消息、Agent  transcripts、搜索索引"
    app_hint = "请先完全关闭 Cursor 后再清理，否则数据库可能被占用。"

    def locations(self) -> list[tuple[Path, str]]:
        home = Path.home()
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        return [
            (
                appdata / "Cursor" / "User" / "globalStorage" / "state.vscdb",
                "全局 state.vscdb（侧边栏会话列表 + 消息内容）",
            ),
            (
                home / ".cursor" / "projects",
                "各项目的 agent-transcripts（Agent 对话记录）",
            ),
            (
                appdata / "Cursor" / "User" / "globalStorage" / "conversation-search.db",
                "对话搜索索引数据库",
            ),
        ]

    def clean(self, dry_run: bool = True, log=None):
        result = CleanResult(self.target_id, self.label)
        home = Path.home()
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))

        rows, freed = clean_all_cursor_vscdb(dry_run=dry_run, log=log)
        result.deleted_files += rows
        result.freed_bytes += freed

        projects_root = home / ".cursor" / "projects"
        if projects_root.exists():
            project_dirs = [p for p in projects_root.iterdir() if p.is_dir()]
            emit_log(log, f"  清理 agent-transcripts（{len(project_dirs)} 个项目）…")
            for project_dir in project_dirs:
                transcripts = project_dir / "agent-transcripts"
                if not transcripts.exists():
                    continue
                emit_log(log, f"    删除: {transcripts}")
                try:
                    for child in list(transcripts.iterdir()):
                        f, d, b = remove_path(child, dry_run)
                        result.deleted_files += f
                        result.deleted_dirs += d
                        result.freed_bytes += b
                except OSError as exc:
                    result.errors.append(f"agent-transcripts ({transcripts}): {exc}")
        else:
            result.skipped.append("Cursor projects 目录不存在")

        gs = appdata / "Cursor" / "User" / "globalStorage"
        for name in (
            "conversation-search.db",
            "conversation-search.db-wal",
            "conversation-search.db-shm",
        ):
            db_path = gs / name
            if not db_path.exists():
                continue
            emit_log(log, f"  删除文件: {db_path}")
            try:
                f, d, b = remove_path(db_path, dry_run)
                result.deleted_files += f
                result.deleted_dirs += d
                result.freed_bytes += b
            except OSError as exc:
                result.errors.append(f"{name}: {exc}")

        return result

    def scan(self, log=None):
        items: list[ScanItem] = []
        home = Path.home()
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        projects_root = home / ".cursor" / "projects"

        emit_log(log, "  [1/3] Cursor 侧边栏 / Composer 对话")
        db_count, chat_rows, chat_bytes = scan_all_cursor_vscdb(log=log)
        global_db = cursor_user_root() / "globalStorage" / "state.vscdb"
        items.append(
            ScanItem(
                global_db,
                "state.vscdb 对话记录汇总",
                global_db.exists(),
                chat_rows,
                db_count,
                chat_bytes,
            )
        )

        emit_log(log, "  [2/3] agent-transcripts")
        transcript_files = transcript_dirs = transcript_bytes = 0
        if projects_root.exists():
            project_dirs = sorted(p for p in projects_root.iterdir() if p.is_dir())
            emit_log(log, f"  扫描目录: {projects_root}（{len(project_dirs)} 个项目）")
            hit = 0
            for project_dir in project_dirs:
                transcripts = project_dir / "agent-transcripts"
                if not transcripts.exists():
                    continue
                hit += 1
                emit_log(log, f"  [{hit}] {transcripts}")
                f, d = count_items(transcripts)
                b = path_size(transcripts)
                transcript_files += f
                transcript_dirs += d
                transcript_bytes += b
                emit_log(log, f"       → {f} 文件, {format_bytes(b)}")
        else:
            emit_log(log, f"  目录不存在: {projects_root}")

        items.append(
            ScanItem(
                projects_root,
                "agent-transcripts 汇总",
                projects_root.exists(),
                transcript_files,
                transcript_dirs,
                transcript_bytes,
            )
        )

        emit_log(log, "  [3/3] 对话搜索索引")
        for raw_path, desc in self.locations()[2:]:
            path = expand(raw_path)
            emit_log(log, f"  检查: {path}")
            exists = path.exists()
            size = path.stat().st_size if exists and path.is_file() else 0
            emit_log(log, f"       → {'存在, ' + format_bytes(size) if exists else '不存在'}")
            items.append(ScanItem(path, desc, exists, 1 if exists else 0, 0, size))

        for db_path, desc in iter_cursor_vscdb_files()[1:]:
            rows, size = scan_vscdb_chat(db_path)
            if rows:
                items.append(
                    ScanItem(db_path, desc, True, rows, 0, size)
                )

        return items
