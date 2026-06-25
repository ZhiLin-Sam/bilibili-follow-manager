"""审查页面 — 表格浏览 + 搜索 + 标记删除/保留"""

import tkinter as tk
import tkinter.ttk as ttk
from tkinter import messagebox

from .. import pages as page_registry
from ..db import database
from ..theme import ACCENT, BG0, BG2, FG0, GREEN, RED, YELLOW
from .base import BasePage

# 8 核心列定义
CORE_COLS = [
    ("mid", "UID", 80),
    ("uname", "用户名", 120),
    ("sign", "签名", 200),
    ("official", "认证", 100),
    ("verdict", "判定", 70),
    ("delete_score", "删除分", 60),
    ("archive_count", "投稿", 50),
    ("follower", "粉丝", 60),
]

# 扩展列 (右键可展开)
EXTRA_COLS = [
    ("vip", "VIP", 60),
    ("level", "等级", 40),
    ("total_view", "播放量", 80),
    ("ff_ratio", "关注/粉丝比", 80),
    ("spacesta", "状态", 50),
    ("mtime", "关注时间", 130),
    ("rule_keep", "保留规则", 120),
    ("rule_delete", "删除规则", 120),
]

ALL_COLS = CORE_COLS + EXTRA_COLS


@page_registry.register_page
class ReviewPage(BasePage):
    page_id = "review"
    title = "审查"
    order = 3

    def _build_icon(self):
        from ..app import _icon_review, _make_icon
        return _make_icon(_icon_review)

    def _build(self, parent: ttk.Frame) -> None:
        super()._build(parent)
        f = parent

        # 标题栏
        hdr = ttk.Frame(f)
        hdr.pack(fill=tk.X)
        ttk.Label(hdr, text="审查关注列表", style="Header.TLabel").pack(side=tk.LEFT)
        self.count_var = tk.StringVar(value="共 0 条")
        ttk.Label(hdr, textvariable=self.count_var, style="Subtitle.TLabel").pack(side=tk.RIGHT)

        # 搜索 + 操作栏
        ctrl = ttk.Frame(f)
        ctrl.pack(fill=tk.X, pady=(5, 10))

        ttk.Label(ctrl, text="搜索:").pack(side=tk.LEFT, padx=(0, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_search())
        search = ttk.Entry(ctrl, textvariable=self.search_var, width=30)
        search.pack(side=tk.LEFT, padx=(0, 8))

        # 判定筛选
        ttk.Label(ctrl, text="筛选:").pack(side=tk.LEFT, padx=(0, 4))
        self.filter_var = tk.StringVar(value="全部")
        self._filter_cb = ttk.Combobox(ctrl, textvariable=self.filter_var,
            values=["全部", "待审", "保留", "删除", "保护"],
            state="readonly", width=8)
        self._filter_cb.pack(side=tk.LEFT, padx=(0, 8))
        self._filter_cb.bind("<<ComboboxSelected>>", lambda _: self._refresh())

        # 操作按钮
        ttk.Button(ctrl, text="标记保留", command=lambda: self._set_verdict("keep")).pack(side=tk.LEFT, padx=2)
        ttk.Button(ctrl, text="标记删除", command=lambda: self._set_verdict("delete")).pack(side=tk.LEFT, padx=2)
        ttk.Button(ctrl, text="重置判定", command=lambda: self._set_verdict("unreviewed")).pack(side=tk.LEFT, padx=2)
        ttk.Button(ctrl, text="🔄 刷新", command=self._refresh).pack(side=tk.RIGHT)

        # ── Treeview ──
        tree_frame = ttk.Frame(f)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        col_ids = [c[0] for c in CORE_COLS]
        self.tree = ttk.Treeview(tree_frame, columns=col_ids, show="headings",
                                  selectmode="extended")
        for col_id, col_name, col_width in CORE_COLS:
            self.tree.heading(col_id, text=col_name,
                              command=lambda c=col_id: self._sort_by_col(c))
            self.tree.column(col_id, width=col_width, minwidth=40, stretch=col_id in ("sign",))

        # 滚动条
        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # 右键菜单
        self.tree.bind("<Button-3>", self._on_right_click)
        # 双击查看详情
        self.tree.bind("<Double-1>", self._on_double_click)

        # 标签色
        self.tree.tag_configure("keep", foreground=GREEN)
        self.tree.tag_configure("delete", foreground=RED)
        self.tree.tag_configure("protected", foreground=ACCENT)
        self.tree.tag_configure("unreviewed", foreground=YELLOW)

        self._sort_col: str | None = None
        self._sort_asc = True
        self._all_data: list[dict] = []

        self._refresh()

    def on_enter(self):
        self._refresh()

    # ── 数据刷新 ──

    def _refresh(self):
        self._all_data = database.get_all_with_verdicts()
        self._apply_search()
        self._update_count()

    def _update_count(self):
        self.count_var.set(f"共 {len(self._all_data)} 条")

    def _apply_search(self):
        query = self.search_var.get().lower()
        vf = self.filter_var.get()
        ver_map = {"保留": "keep", "删除": "delete", "保护": "protected", "待审": "unreviewed"}

        self.tree.delete(*self.tree.get_children())

        for row in self._all_data:
            # 判定筛选
            verdict = row.get("verdict", "unreviewed") or "unreviewed"
            if vf in ver_map and verdict != ver_map[vf]:
                continue

            # 文本搜索
            if query:
                match = False
                for col_id, _, _ in ALL_COLS:
                    val = str(row.get(col_id, "") or "").lower()
                    if query in val:
                        match = True
                        break
                if not match:
                    continue

            verdict_disp = {"keep": "保留", "delete": "删除", "protected": "保护⭐"}.get(verdict, "待审")
            official = row.get("official_verify_desc", "") or ""

            vals = {
                "mid": row["mid"],
                "uname": row.get("uname", ""),
                "sign": (row.get("sign", "") or "")[:60],
                "official": official[:12],
                "verdict": verdict_disp,
                "delete_score": row.get("delete_score", 0),
                "archive_count": row.get("archive_count", -1) if row.get("archive_count") != -1 else "?",
                "follower": row.get("probe_follower", -1) if row.get("probe_follower", -1) != -1 else "?",
            }
            item_vals = [vals.get(c[0], "") for c in CORE_COLS]
            self.tree.insert("", tk.END, values=item_vals, tags=(verdict,))

        # 排序
        if self._sort_col:
            self._sort(self._sort_col)

    # ── 排序 ──

    def _sort_by_col(self, col: str) -> None:
        """排序回调包装 (避免 lambda 类型推断问题)"""
        self._sort(col)

    def _sort(self, col: str):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True

        sort_col: str = col
        items = [(self.tree.set(k, sort_col), k) for k in self.tree.get_children("")]
        try:
            items.sort(key=lambda x: float(x[0]) if x[0].replace(".", "").replace("-", "").isdigit() else x[0],
                       reverse=not self._sort_asc)
        except Exception:
            items.sort(key=lambda x: x[0], reverse=not self._sort_asc)

        for idx, (_, k) in enumerate(items):
            self.tree.move(k, "", idx)

    # ── 右键菜单 ──

    def _on_right_click(self, event):
        sel = self.tree.selection()
        menu = tk.Menu(self.tree, tearoff=0, bg=BG2, fg=FG0)
        if sel:
            menu.add_command(label="复制 UID", command=self._copy_uids)
            menu.add_command(label="标记保留", command=lambda: self._set_verdict("keep"))
            menu.add_command(label="标记删除", command=lambda: self._set_verdict("delete"))
            menu.add_separator()
        menu.add_command(label="展开额外列", command=self._show_extra_cols)
        menu.add_command(label="导出 CSV", command=self._export_csv)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _copy_uids(self):
        uids = []
        for i in self.tree.selection():
            uids.append(self.tree.item(i)["values"][0])
        if uids:
            self.tree.clipboard_clear()
            self.tree.clipboard_append("\n".join(str(u) for u in uids))
            self.log(f"已复制 {len(uids)} 个 UID")

    def _show_extra_cols(self):
        """弹窗显示额外列"""
        dlg = tk.Toplevel(self.app)
        dlg.title("额外列")
        dlg.geometry("400x300")
        dlg.transient(self.app)
        dlg.configure(bg=BG0)

        tree = ttk.Treeview(dlg, columns=["field", "value"], show="headings")
        tree.heading("field", text="字段")
        tree.heading("value", text="值")
        tree.column("field", width=120)
        tree.column("value", width=250)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        sel = self.tree.selection()
        if sel:
            uid = self.tree.item(sel[0])["values"][0]
            for row in self._all_data:
                if str(row["mid"]) == str(uid):
                    for col_id, col_name in [("mid", "UID")] + [(c[0], c[1]) for c in ALL_COLS]:
                        val = row.get(col_id, "")
                        tree.insert("", tk.END, values=(col_name, val))
                    break

        ttk.Button(dlg, text="关闭", command=dlg.destroy).pack(pady=5)

    def _on_double_click(self, event):
        self._show_extra_cols()

    # ── 导出 ──

    def _export_csv(self):
        import csv
        from tkinter import filedialog

        fp = filedialog.asksaveasfilename(defaultextension=".csv",
            filetypes=[("CSV", "*.csv")], title="导出")
        if not fp:
            return

        cols = [c[0] for c in ALL_COLS]
        with open(fp, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow([c[1] for c in ALL_COLS])
            for row in self._all_data:
                w.writerow([row.get(c, "") for c in cols])
        self.log(f"已导出: {fp}")

    # ── 判定 ──

    def _set_verdict(self, verdict: str):
        sel = self.tree.selection()
        if not sel:
            return
        rejected = []
        changed = 0
        verdict_disp_map = {"keep": "保留", "delete": "删除", "protected": "保护⭐", "unreviewed": "待审"}

        for item in sel:
            mid = self.tree.item(item)["values"][0]
            conn = database.get_conn()
            row = conn.execute("SELECT verdict FROM verdicts WHERE mid = ?", (mid,)).fetchone()
            conn.close()
            current = row["verdict"] if row else "unreviewed"
            if current == "protected" and verdict == "delete":
                rejected.append(self.tree.item(item)["values"][1])
                continue

            database.save_verdicts([{"mid": mid, "verdict": verdict}])
            changed += 1

            # 原地更新 Treeview 行 — 不触发全量刷新
            col_idx = 4  # "verdict" 列 (CORE_COLS 第5列, 0-indexed=4)
            vals = list(self.tree.item(item)["values"])
            vals[col_idx] = verdict_disp_map.get(verdict, verdict)
            # 移除旧 tags，只保留非判定 tag（这里旧 tag 就是原 verdict），全部替换
            new_tags = (verdict,)
            self.tree.item(item, values=vals, tags=new_tags)

            # 同步 _all_data
            for row_data in self._all_data:
                if str(row_data["mid"]) == str(mid):
                    row_data["verdict"] = verdict
                    break

        if rejected:
            messagebox.showwarning("保护中", "以下账号已锁定保护:\n" + "\n".join(rejected))
        self._update_count()
        self.log(f"已标记 {changed} 条 → {verdict}" +
                 (f" ({len(rejected)} 条被保护拒绝)" if rejected else ""))
