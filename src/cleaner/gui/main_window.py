from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cleaner.gui.worker import do_clean, do_scan, run_in_thread
from cleaner.service import build_target_groups
from cleaner.targets.base import ChatTarget
from cleaner.utils import format_bytes
from cleaner.wsl import list_wsl_distros, wsl_available


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI 对话清理工具")
        self.resize(980, 760)
        self._checkboxes: dict[str, QCheckBox] = {}
        self._active_thread = None
        self._active_worker = None
        self._active_task = ""
        self._build_ui()
        self._refresh_target_groups()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        header = QLabel("清除 Cursor / VS Code Copilot / Codex 的本地对话记录")
        header.setStyleSheet("font-size: 14px; font-weight: 600;")
        root.addWidget(header)

        hint = QLabel("清理前请关闭对应编辑器。WSL 目标通过 wsl.exe 操作 Linux 文件系统。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        root.addWidget(hint)

        wsl_row = QHBoxLayout()
        wsl_row.addWidget(QLabel("WSL 发行版:"))
        self.wsl_combo = QComboBox()
        self.wsl_combo.setMinimumWidth(180)
        self.wsl_combo.currentTextChanged.connect(self._refresh_target_groups)
        wsl_row.addWidget(self.wsl_combo)
        wsl_row.addStretch()
        root.addLayout(wsl_row)

        self.target_area = QScrollArea()
        self.target_area.setWidgetResizable(True)
        self.target_container = QWidget()
        self.target_layout = QVBoxLayout(self.target_container)
        self.target_area.setWidget(self.target_container)
        self.target_area.setMaximumHeight(200)
        root.addWidget(self.target_area)

        btn_row = QHBoxLayout()
        self.scan_btn = QPushButton("扫描")
        self.clean_btn = QPushButton("清除")
        self.dry_run_cb = QCheckBox("模拟运行（不实际删除）")
        self.select_all_btn = QPushButton("全选")
        self.select_none_btn = QPushButton("全不选")
        btn_row.addWidget(self.scan_btn)
        btn_row.addWidget(self.clean_btn)
        btn_row.addWidget(self.dry_run_cb)
        btn_row.addStretch()
        btn_row.addWidget(self.select_all_btn)
        btn_row.addWidget(self.select_none_btn)
        root.addLayout(btn_row)

        self.summary_label = QLabel("尚未扫描")
        self.summary_label.setStyleSheet("font-weight: 600;")
        root.addWidget(self.summary_label)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["目标", "描述", "路径", "文件", "目录", "大小"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        root.addWidget(self.table, stretch=2)

        root.addWidget(QLabel("日志"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.log.setPlaceholderText("扫描与清理的详细日志均显示在此处…")
        root.addWidget(self.log, stretch=1)

        self.scan_btn.clicked.connect(self._on_scan)
        self.clean_btn.clicked.connect(self._on_clean)
        self.select_all_btn.clicked.connect(lambda: self._set_all_checks(True))
        self.select_none_btn.clicked.connect(lambda: self._set_all_checks(False))

        self._reload_wsl_distros()

    def _reload_wsl_distros(self):
        self.wsl_combo.blockSignals(True)
        self.wsl_combo.clear()
        if wsl_available():
            for distro in list_wsl_distros():
                self.wsl_combo.addItem(distro)
        else:
            self.wsl_combo.addItem("（未检测到 WSL）")
            self.wsl_combo.setEnabled(False)
        self.wsl_combo.blockSignals(False)

    def _selected_wsl_distro(self) -> str | None:
        if not self.wsl_combo.isEnabled():
            return None
        text = self.wsl_combo.currentText().strip()
        if not text or text.startswith("（"):
            return None
        return text

    def _refresh_target_groups(self):
        while self.target_layout.count():
            item = self.target_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._checkboxes.clear()

        groups = build_target_groups(self._selected_wsl_distro())
        for group in groups:
            box = QGroupBox(group.label)
            layout = QVBoxLayout(box)
            for target in group.targets:
                cb = QCheckBox(f"{target.label} — {target.description}")
                cb.setChecked(True)
                cb.setToolTip(target.app_hint)
                self._checkboxes[target.target_id] = cb
                layout.addWidget(cb)
            self.target_layout.addWidget(box)
        self.target_layout.addStretch()

    def _set_all_checks(self, checked: bool):
        for cb in self._checkboxes.values():
            cb.setChecked(checked)

    def _selected_targets(self) -> list[ChatTarget]:
        groups = build_target_groups(self._selected_wsl_distro())
        selected_ids = {
            tid for tid, cb in self._checkboxes.items() if cb.isChecked()
        }
        return [t for g in groups for t in g.targets if t.target_id in selected_ids]

    def _set_busy(self, busy: bool):
        self.scan_btn.setEnabled(not busy)
        self.clean_btn.setEnabled(not busy)
        self.wsl_combo.setEnabled(not busy and wsl_available())

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _append_log(self, text: str):
        self.log.appendPlainText(text)
        scrollbar = self.log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        QApplication.processEvents()

    def _start_task(self, task: str, fn, on_done, *args, **kwargs):
        if self._active_thread is not None and self._active_thread.isRunning():
            QMessageBox.warning(self, "提示", "当前有任务正在运行，请稍候。")
            return False

        self._active_task = task
        self._active_thread, self._active_worker = run_in_thread(
            self,
            fn,
            on_done,
            self._on_task_failed,
            self._append_log,
            *args,
            **kwargs,
        )
        return True

    def _on_scan(self):
        targets = self._selected_targets()
        if not targets:
            QMessageBox.warning(self, "提示", "请至少选择一个清理目标。")
            return

        self._set_busy(True)
        self.summary_label.setText("正在扫描…")
        self._append_log("")
        self._append_log(f"[{self._timestamp()}] ── 扫描 ── 共 {len(targets)} 个目标")
        for target in targets:
            self._append_log(f"  · {target.label}")

        if not self._start_task("scan", do_scan, self._on_scan_done, targets):
            self._set_busy(False)

    def _on_scan_done(self, summaries):
        self._set_busy(False)
        self._active_thread = None
        self._active_worker = None
        self._active_task = ""

        self.table.setRowCount(0)
        total_files = total_dirs = total_bytes = 0
        for summary in summaries:
            target = summary.target
            for item in summary.items:
                row = self.table.rowCount()
                self.table.insertRow(row)
                values = [
                    target.label,
                    item.description,
                    str(item.path),
                    str(item.file_count) if item.exists else "-",
                    str(item.dir_count) if item.exists else "-",
                    format_bytes(item.size_bytes) if item.exists else "-",
                ]
                for col, value in enumerate(values):
                    cell = QTableWidgetItem(value)
                    if col >= 3:
                        cell.setTextAlignment(
                            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                        )
                    self.table.setItem(row, col, cell)
            total_files += summary.total_files
            total_dirs += summary.total_dirs
            total_bytes += summary.total_bytes

        self.summary_label.setText(
            f"合计: 文件 {total_files}, 目录 {total_dirs}, 大小 {format_bytes(total_bytes)}"
        )
        self._append_log(
            f"[{self._timestamp()}] 扫描完成 — 文件 {total_files}, "
            f"目录 {total_dirs}, 大小 {format_bytes(total_bytes)}"
        )

    def _on_clean(self):
        targets = self._selected_targets()
        if not targets:
            QMessageBox.warning(self, "提示", "请至少选择一个清理目标。")
            return

        dry_run = self.dry_run_cb.isChecked()
        if not dry_run:
            labels = "\n".join(f"• {t.label}" for t in targets)
            answer = QMessageBox.warning(
                self,
                "确认清除",
                f"即将永久删除以下目标的对话数据：\n\n{labels}\n\n此操作不可恢复，是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        self._set_busy(True)
        mode = "模拟清除" if dry_run else "清除"
        self.summary_label.setText(f"正在{mode}…")
        self._append_log("")
        self._append_log(f"[{self._timestamp()}] ── {mode} ── 共 {len(targets)} 个目标")
        for target in targets:
            self._append_log(f"  · {target.label}")

        if not self._start_task(
            "clean",
            do_clean,
            self._on_clean_done,
            targets,
            dry_run,
        ):
            self._set_busy(False)

    def _on_clean_done(self, results):
        self._set_busy(False)
        self._active_thread = None
        self._active_worker = None
        self._active_task = ""

        freed = sum(r.freed_bytes for r in results)
        files = sum(r.deleted_files for r in results)
        dirs = sum(r.deleted_dirs for r in results)
        dry_run = self.dry_run_cb.isChecked()

        for result in results:
            for msg in result.skipped:
                self._append_log(f"  跳过: {msg}")
            for msg in result.errors:
                self._append_log(f"  错误: {msg}")

        suffix = "（模拟）" if dry_run else ""
        self._append_log(
            f"[{self._timestamp()}] {mode_label(dry_run)}完成{suffix} — "
            f"文件 {files}, 目录 {dirs}, 释放 {format_bytes(freed)}"
        )

        if not dry_run:
            QMessageBox.information(
                self,
                "完成",
                f"清理完成。\n释放 {format_bytes(freed)}\n请重启对应编辑器以刷新界面。",
            )
            self._append_log(f"[{self._timestamp()}] 清理后自动重新扫描…")
            self._on_scan()

    def _on_task_failed(self, message: str):
        self._set_busy(False)
        self._active_thread = None
        self._active_worker = None
        self._append_log(f"[{self._timestamp()}] 错误: {message}")
        self._active_task = ""
        QMessageBox.critical(self, "错误", message)


def mode_label(dry_run: bool) -> str:
    return "模拟清除" if dry_run else "清除"
