"""取关页面 — 左名单 + 右操作 单页确认面板"""

import threading
import tkinter as tk
import tkinter.ttk as ttk
from tkinter import messagebox

from .base import BasePage
from .. import pages as page_registry
from ..db import database
from ..api.unfollow import batch_unfollow
from ..theme import BG0, BG1, BG2, FG0, FG1, ACCENT, RED, GREEN


@page_registry.register_page
class UnfollowPage(BasePage):
    page_id = "unfollow"
    title = "取关"
    order = 4

    def _build_icon(self):
        from ..app import _icon_unfollow, _make_icon
        return _make_icon(_icon_unfollow)

    def _build(self, parent: ttk.Frame) -> None:
        super()._build(parent)
        f = parent

        ttk.Label(f, text="取消关注", style="Header.TLabel").pack(anchor="w", pady=(0, 5))
        ttk.Label(f, text="确认待删除账号 → 输入 DELETE → 执行",
                  style="Subtitle.TLabel").pack(anchor="w", pady=(0, 10))

        # ── 左右分栏 ──
        pw = ttk.PanedWindow(f, orient=tk.HORIZONTAL)
        pw.pack(fill=tk.BOTH, expand=True)

        # 左侧: 名单
        left = ttk.Frame(pw)
        pw.add(left, weight=1)

        ttk.Label(left, text="待取关账号", style="Subtitle.TLabel").pack(anchor="w", pady=(0, 5))

        list_frame = ttk.Frame(left)
        list_frame.pack(fill=tk.BOTH, expand=True)
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        scroll = ttk.Scrollbar(list_frame)
        self.unfollow_list = tk.Listbox(list_frame, bg=BG2, fg=FG0, font=("Cascadia Code", 9),
                                         selectmode=tk.EXTENDED, selectbackground=ACCENT,
                                         selectforeground="#ffffff",
                                         yscrollcommand=scroll.set)
        scroll.configure(command=self.unfollow_list.yview)
        self.unfollow_list.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        btn_left = ttk.Frame(left)
        btn_left.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(btn_left, text="全选", command=self._select_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_left, text="取消全选", command=self._deselect_all).pack(side=tk.LEFT, padx=2)

        # 右侧: 操作
        right = ttk.Frame(pw)
        pw.add(right, weight=1)

        # 统计
        self.unfollow_count_var = tk.StringVar(value="待取关: 0")
        ttk.Label(right, textvariable=self.unfollow_count_var,
                  style="Subtitle.TLabel").pack(anchor="w", pady=(0, 5))

        self.selected_count_var = tk.StringVar(value="已选: 0")
        ttk.Label(right, textvariable=self.selected_count_var,
                  style="Subtitle.TLabel").pack(anchor="w", pady=(0, 10))
        self.unfollow_list.bind("<<ListboxSelect>>", lambda _: self._update_selected())

        # 确认输入
        ttk.Label(right, text="输入 DELETE 确认操作:").pack(anchor="w", pady=(10, 2))
        self.confirm_var = tk.StringVar()
        self.confirm_var.trace_add("write", self._on_confirm_change)
        self.confirm_entry = ttk.Entry(right, textvariable=self.confirm_var,
                                        width=24, font=("Cascadia Code", 14))
        self.confirm_entry.pack(anchor="w", pady=(0, 5))

        self._ok_label = ttk.Label(right, text="", style="Success.TLabel")
        self._ok_label.pack(anchor="w")

        # 执行按钮
        self.exec_btn = ttk.Button(right, text="⚠ 执行取关 (不可撤销!)",
                                    style="Danger.TButton", command=self._execute,
                                    state=tk.DISABLED)
        self.exec_btn.pack(anchor="w", pady=(10, 5))

        self._btn_stop = ttk.Button(right, text="⏹ 停止", command=self._stop_op,
                                     state=tk.DISABLED)
        self._btn_stop.pack(anchor="w")

        self._op_active = False
        self._stop_requested = False

        # 进度 + 日志
        self.progress = ttk.Progressbar(right, mode="determinate")
        self.progress.pack(fill=tk.X, pady=(10, 5))

        log_frame = ttk.Frame(right)
        log_frame.pack(fill=tk.BOTH, expand=True)
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        log_scroll = ttk.Scrollbar(log_frame)
        self.unfollow_log = tk.Text(log_frame, bg=BG2, fg=FG0, font=("Cascadia Code", 8),
                                     height=10, yscrollcommand=log_scroll.set)
        log_scroll.configure(command=self.unfollow_log.yview)
        self.unfollow_log.grid(row=0, column=0, sticky="nsew")
        log_scroll.grid(row=0, column=1, sticky="ns")

    def on_enter(self):
        self._refresh()

    def _refresh(self):
        conn = database.get_conn()
        rows = conn.execute(
            "SELECT f.mid, f.uname FROM follows f "
            "JOIN verdicts v ON f.mid = v.mid WHERE v.verdict = 'delete'"
        ).fetchall()
        conn.close()

        self.unfollow_list.delete(0, tk.END)
        for r in rows:
            self.unfollow_list.insert(tk.END, f"{r['mid']}  {r['uname']}")

        self.unfollow_count_var.set(f"待取关: {len(rows)}")
        self.selected_count_var.set("已选: 0")
        self._on_confirm_change()

    def _select_all(self):
        self.unfollow_list.select_set(0, tk.END)
        self._update_selected()

    def _deselect_all(self):
        self.unfollow_list.selection_clear(0, tk.END)
        self._update_selected()

    def _update_selected(self):
        sel = self.unfollow_list.curselection()
        self.selected_count_var.set(f"已选: {len(sel)}")
        self._on_confirm_change()

    def _on_confirm_change(self, *_):
        sel = self.unfollow_list.curselection()
        ok = len(sel) > 0 and self.confirm_var.get().strip() == "DELETE"
        self.exec_btn.configure(state=tk.NORMAL if ok else tk.DISABLED)
        self._ok_label.configure(
            text="✅ 已确认，可执行" if ok else "等待确认..."
        )

    def _start_op(self):
        self._op_active = True
        self._stop_requested = False
        self._btn_stop.configure(state=tk.NORMAL)
        self.exec_btn.configure(state=tk.DISABLED)

    def _end_op(self):
        self._op_active = False
        self._stop_requested = False
        self._btn_stop.configure(state=tk.DISABLED)
        self._on_confirm_change()

    def _stop_op(self):
        self._stop_requested = True
        self.log("正在停止...")

    def _execute(self):
        sel = self.unfollow_list.curselection()
        if not sel:
            return
        if self.confirm_var.get().strip() != "DELETE":
            messagebox.showwarning("未确认", "请输入 DELETE 确认操作")
            return

        lines = [self.unfollow_list.get(i) for i in sel]
        uids = [l.split()[0] for l in lines]
        count = len(uids)

        if not messagebox.askyesno("最终确认", f"即将取消关注 {count} 个账号，不可撤销。\n\n确认执行？"):
            return

        if not self.app.client:
            messagebox.showwarning("未登录", "请先登录")
            return

        self._start_op()
        client = self.app.client

        def _run():
            try:
                def progress(done, total, ok):
                    if self._stop_requested:
                        raise RuntimeError("用户停止")
                    pct = (done / total) * 100
                    self.app.ui_call(lambda: self.progress.configure(value=pct))
                    self.app.ui_call(lambda: self.unfollow_log.insert(
                        tk.END, f"[{done}/{total}] 成功: {ok}\n"
                    ))
                    self.app.ui_call(lambda: self.unfollow_log.see(tk.END))

                ok, fail = batch_unfollow(client, uids, interval=3.0,
                                           progress_callback=progress)
                self.app.ui_call(lambda: self.log(f"取关完成: {ok} 成功, {fail} 失败"))

                conn = database.get_conn()
                conn.execute("DELETE FROM verdicts WHERE verdict = 'delete'")
                conn.commit()
                conn.close()

                self.app.ui_call(lambda: [
                    self._refresh(),
                    self.confirm_var.set(""),
                ])
            except RuntimeError:
                self.app.ui_call(lambda: self.log("取关已停止"))
            except Exception as e:
                self.app.ui_call(lambda: self.log(f"取关异常: {e}"))
            finally:
                self.app.ui_call(lambda: [
                    self.progress.configure(value=0),
                    self._end_op()
                ])

        threading.Thread(target=_run, daemon=True).start()
