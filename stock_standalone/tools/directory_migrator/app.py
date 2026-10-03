# -*- coding: utf-8 -*-
"""Tkinter UI for the standalone Windows directory migrator."""

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from migrator_core import (
    MigrationCancelled,
    build_preflight_report,
    find_source_occupants,
    format_source_occupants,
    migrate_directory,
)


class DirectoryMigratorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Windows 目录迁移工具")
        self.root.geometry("900x680")
        self.root.minsize(760, 560)

        self.source_var = tk.StringVar()
        self.destination_var = tk.StringVar()
        self.closed_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="选择源目录和目标位置后，先运行预检查。")
        self.events = queue.Queue()
        self.cancel_event = threading.Event()
        self.busy = False
        self.active_kind = None
        self.preflight_button = None
        self.migrate_button = None
        self.occupancy_button = None
        self.cancel_button = None
        self.progress = None
        self.log = None

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_events)

    def _build_ui(self):
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(7, weight=1)

        ttk.Label(
            frame,
            text="Windows 目录迁移工具",
            font=("Microsoft YaHei UI", 16, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Label(
            frame,
            text="复制并逐项核对后切换原路径；核验通过才清理回退副本。",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0, 14))

        ttk.Label(frame, text="源目录").grid(row=2, column=0, sticky="w", padx=(0, 8))
        source_entry = ttk.Entry(frame, textvariable=self.source_var)
        source_entry.grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Button(frame, text="选择源目录…", command=self._choose_source).grid(
            row=2, column=2, padx=(8, 0), pady=4
        )

        ttk.Label(frame, text="目标完整路径").grid(
            row=3, column=0, sticky="w", padx=(0, 8)
        )
        destination_entry = ttk.Entry(frame, textvariable=self.destination_var)
        destination_entry.grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Button(
            frame,
            text="选择目标父目录…",
            command=self._choose_destination_parent,
        ).grid(row=3, column=2, padx=(8, 0), pady=4)

        ttk.Label(
            frame,
            text="选择目标父目录后，会以源目录名生成目标完整路径；也可以直接编辑目标路径。",
            foreground="#555555",
        ).grid(row=4, column=1, columnspan=2, sticky="w", pady=(0, 8))

        ttk.Checkbutton(
            frame,
            text="我已关闭使用源目录的程序，并确认它们不会在迁移期间写入",
            variable=self.closed_var,
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(2, 8))
        self.occupancy_button = ttk.Button(
            frame, text="检测占用程序", command=self._start_occupancy_check
        )
        self.occupancy_button.grid(row=5, column=2, sticky="e", pady=(2, 8))

        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        self.preflight_button = ttk.Button(
            buttons, text="运行预检查", command=self._start_preflight
        )
        self.preflight_button.pack(side="left")
        self.migrate_button = ttk.Button(
            buttons, text="开始迁移", command=self._confirm_and_start
        )
        self.migrate_button.pack(side="left", padx=(8, 0))
        self.cancel_button = ttk.Button(
            buttons, text="取消（切换前有效）", command=self._cancel, state="disabled"
        )
        self.cancel_button.pack(side="left", padx=(8, 0))

        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(2, 4))
        ttk.Label(frame, textvariable=self.status_var).grid(
            row=8, column=0, columnspan=3, sticky="w", pady=(0, 6)
        )

        self.log = tk.Text(frame, height=18, wrap="word", state="disabled")
        self.log.grid(row=9, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(9, weight=1)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=9, column=3, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

        note = (
            "核对项目：目录结构、文件大小与 SHA-256、修改时间、常见文件属性、"
            "符号链接/目录联接目标及目录内硬链接关系。"
            "遇到 NTFS 备用数据流等未支持内容会中止。"
            "NTFS 权限、所有者和 ACL 由目标父目录继承。"
        )
        ttk.Label(
            frame, text=note, wraplength=850, foreground="#555555"
        ).grid(row=10, column=0, columnspan=3, sticky="w", pady=(8, 0))

    def _choose_source(self):
        selected = filedialog.askdirectory(
            parent=self.root,
            title="选择要迁移的源目录",
            mustexist=True,
        )
        if selected:
            self.source_var.set(os.path.normpath(selected))

    def _choose_destination_parent(self):
        source = self.source_var.get().strip()
        initial = os.path.dirname(self.destination_var.get().strip()) if self.destination_var.get().strip() else ""
        if not initial and source:
            initial = os.path.dirname(source)
        selected = filedialog.askdirectory(
            parent=self.root,
            title="选择目标父目录",
            initialdir=initial or os.path.expanduser("~"),
            mustexist=True,
        )
        if selected:
            folder_name = os.path.basename(source.rstrip("\\/")) if source else "migrated-folder"
            self.destination_var.set(os.path.join(selected, folder_name))

    def _paths_from_fields(self):
        source = self.source_var.get().strip()
        destination = self.destination_var.get().strip()
        if not source or not destination:
            raise ValueError("请先填写源目录和目标完整路径。")
        return source, destination

    def _source_path_from_field(self):
        source = self.source_var.get().strip()
        if not source or not os.path.isdir(source):
            raise ValueError("请先填写有效的源目录。")
        return source

    def _start_occupancy_check(self):
        try:
            source = self._source_path_from_field()
        except ValueError as exc:
            messagebox.showwarning("源目录未填写", str(exc), parent=self.root)
            return
        self._start_worker(
            "occupancy",
            lambda: find_source_occupants(
                source, self._post_progress, self.cancel_event
            ),
        )

    def _start_preflight(self):
        try:
            source, destination = self._paths_from_fields()
        except ValueError as exc:
            messagebox.showwarning("路径未填写", str(exc), parent=self.root)
            return
        self._start_worker(
            "preflight",
            lambda: build_preflight_report(
                source, destination, self._post_progress, self.cancel_event
            ),
        )

    def _confirm_and_start(self):
        if not self.closed_var.get():
            messagebox.showwarning(
                "请先关闭相关程序",
                "迁移前请关闭使用源目录的程序，并勾选确认项。",
                parent=self.root,
            )
            return
        try:
            source, destination = self._paths_from_fields()
        except ValueError as exc:
            messagebox.showwarning("路径未填写", str(exc), parent=self.root)
            return

        accepted = messagebox.askyesno(
            "确认迁移",
            "源目录：\n{}\n\n目标目录：\n{}\n\n"
            "工具会先复制并核对 SHA-256、结构和链接，再把原路径切换为目录联接。"
            "只有最终核验通过后才会自动清理回退副本。\n\n"
            "目标文件继承目标父目录的 ACL；源目录所有者和 ACL 不会复制。"
            "\n\n继续迁移？".format(source, destination),
            parent=self.root,
        )
        if not accepted:
            return
        self._start_worker(
            "migration",
            lambda: migrate_directory(
                source,
                destination,
                confirm_apps_closed=True,
                progress=self._post_progress,
                cancel_event=self.cancel_event,
            ),
        )

    def _start_worker(self, kind, operation):
        if self.busy:
            return
        self.busy = True
        self.active_kind = kind
        self.cancel_event.clear()
        self.preflight_button.configure(state="disabled")
        self.migrate_button.configure(state="disabled")
        self.occupancy_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.progress.configure(mode="indeterminate")
        self.progress.start(12)
        labels = {
            "preflight": "预检查",
            "occupancy": "占用检测",
            "migration": "迁移",
        }
        label = labels[kind]
        self.status_var.set("正在执行{}…".format(label))
        self._append_log("\n=== {} ===".format(label))

        def worker():
            try:
                result = operation()
                self.events.put({"type": "result", "kind": kind, "result": result})
            except MigrationCancelled as exc:
                self.events.put({"type": "cancelled", "message": str(exc)})
            except Exception as exc:
                self.events.put({"type": "error", "message": str(exc)})
            finally:
                self.events.put({"type": "finished"})

        threading.Thread(target=worker, name="directory-migration", daemon=True).start()

    def _post_progress(self, event):
        self.events.put({"type": "progress", "event": event})

    def _cancel(self):
        if self.busy:
            self.cancel_event.set()
            if self.active_kind in ("occupancy", "preflight"):
                self.status_var.set("正在取消只读检测…")
            else:
                self.status_var.set("正在请求取消；原路径切换开始后会完成安全核验。")

    def _poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _handle_event(self, event):
        kind = event.get("type")
        if kind == "progress":
            self._handle_progress(event["event"])
        elif kind == "result":
            if event["kind"] == "preflight":
                self._show_preflight(event["result"])
            elif event["kind"] == "occupancy":
                self._show_occupants(event["result"])
            else:
                self._show_result(event["result"])
        elif kind == "error":
            self._append_log("失败：{}".format(event["message"]))
            self.status_var.set("操作未完成，请查看检测结果。")
            messagebox.showerror("操作未完成", event["message"], parent=self.root)
        elif kind == "cancelled":
            self._append_log(event["message"])
            self.status_var.set("操作已安全取消。")
        elif kind == "finished":
            self.busy = False
            self.active_kind = None
            self.progress.stop()
            self.progress.configure(mode="indeterminate")
            self.progress["value"] = 0
            self.preflight_button.configure(state="normal")
            self.migrate_button.configure(state="normal")
            self.occupancy_button.configure(state="normal")
            self.cancel_button.configure(state="disabled")

    def _handle_progress(self, event):
        stage = event.get("stage", "")
        path = event.get("path", "")
        labels = {
            "check_occupants": "检测源目录占用进程",
            "scan_source": "扫描源目录",
            "scan": "计算 SHA-256",
            "hash": "读取文件",
            "copy_start": "复制到目标临时目录",
            "copy": "复制文件",
            "copy_link": "复制链接",
            "verify_copy": "核对临时副本",
            "verify_source_unchanged": "检查源目录是否变化",
            "install_destination": "安装核验通过的目标目录",
            "verify_destination": "核对目标目录",
            "switch_source": "切换原路径为目录联接",
            "verify_final": "最终双边核验",
            "cleanup_backup": "核验通过，清理回退副本",
            "complete": "迁移完成",
        }
        label = labels.get(stage)
        if label:
            if stage == "check_occupants" and "checked" in event:
                label = "{}（已登记 {} 个文件）".format(label, event["checked"])
            self.status_var.set("{}{}".format(label, "：{}".format(path) if path else "…"))
        if stage in (
            "scan_source", "scan", "hash", "verify_copy",
            "verify_source_unchanged", "verify_destination", "verify_final",
        ):
            self.progress.stop()
            self.progress.configure(mode="indeterminate")
            self.progress.start(12)
        if stage == "switch_source":
            self.cancel_button.configure(state="disabled")
        if stage in ("copy", "hash") and event.get("total_bytes"):
            self.progress.stop()
            self.progress.configure(mode="determinate", maximum=100)
            percent = min(
                100,
                int(event.get("bytes", 0) * 100 / max(1, event["total_bytes"])),
            )
            self.progress["value"] = percent
        if stage == "complete":
            self.progress.stop()
            self.progress.configure(mode="determinate", maximum=100)
            self.progress["value"] = 100

    def _show_preflight(self, report):
        occupants = report.get("occupants", [])
        if occupants:
            self._append_log("源目录：{}".format(report["source"]))
            self._append_log("目标目录：{}".format(report["destination"]))
            self._append_occupant_lines(occupants)
            self.status_var.set("预检查已提前停止：请先关闭占用程序。")
            messagebox.showwarning(
                "源目录仍被占用",
                "已优先检测到以下程序正在使用源目录，完整预检查已停止。"
                "关闭这些程序后再运行预检查：\n\n{}".format(
                    format_source_occupants(occupants)
                ),
                parent=self.root,
            )
            return

        inventory = report["inventory"]
        self._append_log("源目录：{}".format(report["source"]))
        self._append_log("目标目录：{}".format(report["destination"]))
        self._append_log(
            "预检查通过：{} 个文件，{} 个目录，{} 个链接；数据 {:.2f} GB。".format(
                inventory.file_count,
                inventory.directory_count,
                inventory.link_count,
                inventory.total_bytes / (1024 ** 3),
            )
        )
        self._append_log(
            "文件系统：{} -> {}；目标可用空间 {:.2f} GB。".format(
                report["source_filesystem"],
                report["destination_filesystem"],
                report["free_bytes"] / (1024 ** 3),
            )
        )
        self._append_occupant_lines(occupants)
        self.status_var.set("预检查通过；未发现占用进程，迁移前会再次检查。")

    def _append_occupant_lines(self, occupants):
        if not occupants:
            self._append_log("占用检测：未发现正在使用源目录文件的程序。")
            return
        self._append_log("占用检测：发现 {} 个程序/服务。".format(len(occupants)))
        for item in occupants:
            self._append_log("  • {} (PID {})".format(item["name"], item["pid"]))

    def _show_occupants(self, occupants):
        self._append_occupant_lines(occupants)
        if occupants:
            self.status_var.set("检测到占用进程；请关闭后再次检测。")
            messagebox.showwarning(
                "源目录仍被占用",
                "以下程序正在使用源目录资源，请关闭程序后重新检测：\n\n{}".format(
                    format_source_occupants(occupants)
                ),
                parent=self.root,
            )
        else:
            self.status_var.set("未发现占用源目录资源的程序。")
            messagebox.showinfo(
                "占用检测完成",
                "未发现正在使用源目录文件的程序。",
                parent=self.root,
            )

    def _show_result(self, result):
        inventory = result.inventory
        self._append_log(
            "SHA-256、文件大小/时间戳/属性、目录结构、硬链接组与链接目标对照完全一致。"
        )
        self._append_log(
            "统计：{} 个文件，{} 个目录，{} 个链接，数据 {:.2f} GB。".format(
                inventory.file_count,
                inventory.directory_count,
                inventory.link_count,
                inventory.total_bytes / (1024 ** 3),
            )
        )
        self._append_log(
            "原路径：{} -> {}".format(result.source, result.destination)
        )
        if result.backup_cleaned:
            self._append_log("最终核验通过，回退副本已清理：{}".format(result.backup))
            self.status_var.set("迁移完成：双边核验通过，回退副本已清理。")
            messagebox.showinfo(
                "迁移完成",
                "双边检测对照完全一致。\n原路径已切换为目录联接，回退副本已清理。",
                parent=self.root,
            )
        else:
            self._append_log(
                "双边核验通过，但回退副本清理未完成，剩余内容位于：{}".format(
                    result.backup
                )
            )
            self.status_var.set("迁移和核验通过；回退副本清理未完成，请检查日志。")
            messagebox.showwarning(
                "迁移已完成，回退副本清理未完成",
                "目录联接和双边核验均已通过，但清理回退副本时遇到问题。"
                "剩余内容可能不完整：\n{}\n\n{}".format(
                    result.backup, result.cleanup_error
                ),
                parent=self.root,
            )

    def _append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _on_close(self):
        if self.busy:
            if self.active_kind in ("occupancy", "preflight"):
                self.cancel_event.set()
                self.root.destroy()
                return
            messagebox.showinfo(
                "操作仍在运行",
                "请等待当前步骤结束。切换阶段不会被强制中断。",
                parent=self.root,
            )
            return
        self.root.destroy()


def main():
    root = tk.Tk()
    DirectoryMigratorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
