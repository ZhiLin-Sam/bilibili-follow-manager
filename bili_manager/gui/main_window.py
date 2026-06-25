"""GUI 主窗口 — Tkinter 实现"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import json
import time
from pathlib import Path

from ..api.client import BiliClient
from ..api.following import fetch_all_followings
from ..api.account import batch_probe
from ..api.unfollow import batch_unfollow
from ..auth.login import login_qrcode, has_valid_cookies, load_cookies
from ..rules.engine import RuleEngine
from ..db import database
from ..utils.helpers import logger, setup_logging, get_data_dir


class BiliGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Bilibili 关注管理器 v0.2")
        self.geometry("1200x750")
        self.minsize(900, 600)

        self.client: BiliClient | None = None
        self.rule_engine = RuleEngine()
        self.follows: list[dict] = []
        self.probes: list[dict] = []
        self._review_data: list[dict] = []
        self.special_follow_uids: set[int] = set()
        self._op_active = False
        self._stop_requested = False

        self._build_ui()
        self._init_db()
        self._after_login_check()

    def _init_db(self):
        try:
            database.init_db()
        except Exception as e:
            self.log(f"数据库初始化失败: {e}")

    def _after_login_check(self):
        if has_valid_cookies():
            cookies = load_cookies()
            if cookies:
                self.client = BiliClient(cookies)
                self.status_var.set(f"已登录 (UID: {self.client.uid})")
                self._enable_tabs()
                self.log(f"自动加载已保存的登录信息, UID: {self.client.uid}")
            return
        self.status_var.set("未登录 — 请先扫码登录")

    # ── 操作防抖 / 停止 ──────────────────────────

    def _start_op(self):
        self._op_active = True
        self._stop_requested = False
        current = self.notebook.index(self.notebook.select())
        for i in range(self.notebook.index("end")):
            if i != current:
                self.notebook.tab(i, state=tk.DISABLED)
        self._stop_btn.configure(state=tk.NORMAL)
        self.update_idletasks()

    def _end_op(self):
        self._op_active = False
        self._stop_requested = False
        for i in range(self.notebook.index("end")):
            self.notebook.tab(i, state=tk.NORMAL)
        self._stop_btn.configure(state=tk.DISABLED)
        self.update_idletasks()

    def _stop_op(self):
        self._stop_requested = True
        self.log("⏹ 正在停止当前操作...")

    # ── UI 构建 ───────────────────────────────────

    def _build_ui(self):
        # 状态栏
        self.status_var = tk.StringVar(value="未登录")
        status_bar = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=4)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self._stop_btn = ttk.Button(status_bar, text="⏹ 停止", command=self._stop_op, state=tk.DISABLED, width=8)
        self._stop_btn.pack(side=tk.RIGHT, padx=4, pady=2)

        # Notebook
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 日志面板 (底部)
        self.log_text = scrolledtext.ScrolledText(self, height=6, state=tk.DISABLED, font=("Consolas", 9))
        self.log_text.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=(0, 5))

        # 各标签页
        self.tab_fetch = self._build_fetch_tab()
        self.tab_filter = self._build_filter_tab()
        self.tab_review = self._build_review_tab()
        self.tab_unfollow = self._build_unfollow_tab()

        self.notebook.add(self.tab_fetch, text="📡 拉取")
        self.notebook.add(self.tab_filter, text="🔍 过滤")
        self.notebook.add(self.tab_review, text="🔍 审查")
        self.notebook.add(self.tab_unfollow, text="🗑 取关")

    def log(self, msg: str):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _enable_tabs(self):
        for i in range(1, self.notebook.index("end")):
            self.notebook.tab(i, state="normal")

    # ── Tab: 拉取关注 ────────────────────────────

    def _build_fetch_tab(self) -> ttk.Frame:
        f = ttk.Frame(self.notebook, padding=10)
        ttk.Label(f, text="登录 & 拉取关注列表", font=("", 12, "bold")).pack(anchor=tk.W)

        # 登录区
        login_frame = ttk.LabelFrame(f, text="登录", padding=10)
        login_frame.pack(fill=tk.X, pady=10)

        ttk.Button(login_frame, text="🔑 扫码登录", command=self._login_qrcode_popup).pack(
            side=tk.LEFT, padx=5)

        self.login_status = tk.StringVar(value="等待登录...")
        ttk.Label(login_frame, textvariable=self.login_status).pack(side=tk.LEFT, padx=20)

        # 拉取区
        fetch_frame = ttk.LabelFrame(f, text="拉取关注", padding=10)
        fetch_frame.pack(fill=tk.X, pady=10)

        ttk.Button(fetch_frame, text="📥 拉取全部关注列表", command=self._fetch_follows).pack(
            side=tk.LEFT, padx=5)

        self.fetch_progress = ttk.Progressbar(fetch_frame, mode="determinate", length=300)
        self.fetch_progress.pack(side=tk.LEFT, padx=10)

        self.fetch_label = tk.StringVar(value="")
        ttk.Label(fetch_frame, textvariable=self.fetch_label).pack(side=tk.LEFT, padx=10)

        return f

    # ── Tab: 过滤 ─────────────────────────────────

    def _build_filter_tab(self) -> ttk.Frame:
        f = ttk.Frame(self.notebook, padding=10)
        ttk.Label(f, text="规则过滤 & 深层探测", font=("", 12, "bold")).pack(anchor=tk.W)

        btns = ttk.Frame(f)
        btns.pack(fill=tk.X, pady=10)
        ttk.Button(btns, text="⚙ 应用签名规则", command=self._apply_rules).pack(side=tk.LEFT, padx=5)
        ttk.Button(btns, text="⭐ 特别关注保护", command=self._fetch_special_follows).pack(side=tk.LEFT, padx=5)
        ttk.Button(btns, text="📝 自定义规则", command=self._open_custom_rules_dialog).pack(side=tk.LEFT, padx=5)
        ttk.Button(btns, text="🔬 深层探测可疑账号", command=self._deep_probe).pack(side=tk.LEFT, padx=5)
        ttk.Button(btns, text="🔧 自定义API", command=self._open_custom_api_dialog).pack(side=tk.LEFT, padx=5)
        ttk.Button(btns, text="📊 刷新统计", command=self._refresh_stats).pack(side=tk.LEFT, padx=5)

        self.filter_progress = ttk.Progressbar(f, mode="determinate")
        self.filter_progress.pack(fill=tk.X, pady=5)

        self.filter_label = tk.StringVar(value="准备就绪")
        ttk.Label(f, textvariable=self.filter_label).pack(anchor=tk.W)

        return f

    # ── Tab: 审查 ─────────────────────────────────

    _COL_FIELD_MAP = {
        "mid": "mid", "uname": "uname", "sign": "sign",
        "official": "official_verify_type", "vip": "vip_type",
        "follower": "probe_follower", "archive_count": "archive_count",
        "level": "level", "total_view": "total_view",
        "ff_ratio": "ff_ratio", "spacesta": "spacesta",
        "mtime": "mtime", "rule_keep": "rule_keep",
        "rule_delete": "rule_delete", "delete_score": "delete_score",
        "verdict": "verdict",
    }

    REVIEW_COLUMNS = [
        ("mid", "UID", 90),
        ("uname", "用户名", 100),
        ("sign", "签名", 180),
        ("official", "认证", 60),
        ("vip", "大会员", 50),
        ("follower", "粉丝", 60),
        ("archive_count", "投稿", 45),
        ("level", "等级", 40),
        ("total_view", "播放量", 70),
        ("ff_ratio", "f/f比", 50),
        ("spacesta", "封禁", 40),
        ("mtime", "关注时间", 100),
        ("rule_keep", "保留规则", 120),
        ("rule_delete", "删除规则", 120),
        ("delete_score", "删除分", 50),
        ("verdict", "判定", 70),
    ]

    def _build_review_tab(self) -> ttk.Frame:
        f = ttk.Frame(self.notebook, padding=10)

        # 顶部工具栏
        toolbar = ttk.Frame(f)
        toolbar.pack(fill=tk.X)

        ttk.Label(toolbar, text="判定:").pack(side=tk.LEFT)
        self.review_filter = tk.StringVar(value="all")
        for label, val in [("全部", "all"), ("待审", "unreviewed"), ("删除", "delete"), ("保留", "keep")]:
            ttk.Radiobutton(toolbar, text=label, variable=self.review_filter, value=val,
                            command=self._refresh_review_table).pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Label(toolbar, text="搜索:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._search_review_table())
        ttk.Entry(toolbar, textvariable=self.search_var, width=18).pack(side=tk.LEFT, padx=2)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        ttk.Button(toolbar, text="列显示", command=self._toggle_column_menu).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="🔄 刷新", command=self._refresh_review_table).pack(side=tk.RIGHT, padx=5)
        ttk.Label(toolbar, textvariable=self._review_count_var()).pack(side=tk.RIGHT, padx=5)

        # Treeview
        tree_frame = ttk.Frame(f)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        col_ids = [c[0] for c in self.REVIEW_COLUMNS]
        self.review_tree = ttk.Treeview(tree_frame, columns=col_ids, show="headings", selectmode="extended")
        for col_id, col_text, col_width in self.REVIEW_COLUMNS:
            self.review_tree.heading(col_id, text=col_text,
                command=lambda c=col_id: self._sort_by_column(c))
            self.review_tree.column(col_id, width=col_width, minwidth=30)

        h_scroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.review_tree.xview)
        v_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.review_tree.yview)
        self.review_tree.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)
        self.review_tree.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # 双击查看详情
        self.review_tree.bind("<Double-1>", self._on_review_double_click)
        # 右键菜单
        self.review_tree.bind("<Button-3>", self._on_tree_right_click)

        # 判定按钮
        action_frame = ttk.Frame(f)
        action_frame.pack(fill=tk.X, pady=5)
        ttk.Button(action_frame, text="🔴 标记删除", command=lambda: self._set_verdict("delete")).pack(side=tk.LEFT, padx=3)
        ttk.Button(action_frame, text="🟢 标记保留", command=lambda: self._set_verdict("keep")).pack(side=tk.LEFT, padx=3)
        ttk.Button(action_frame, text="🔒 保护", command=lambda: self._set_verdict("protected")).pack(side=tk.LEFT, padx=3)
        ttk.Button(action_frame, text="⬜ 取消标记", command=lambda: self._set_verdict("unreviewed")).pack(side=tk.LEFT, padx=3)
        ttk.Button(action_frame, text="💾 保存", command=self._save_all_verdicts).pack(side=tk.RIGHT, padx=5)

        # 默认列可见性
        self._col_visible = {c[0]: tk.BooleanVar(value=True) for c in self.REVIEW_COLUMNS}
        # 隐藏较次要的列
        self._col_visible["rule_keep"].set(False)
        self._col_visible["rule_delete"].set(False)
        self._col_visible["ff_ratio"].set(False)
        self._col_visible["mtime"].set(False)

        return f

    def _review_count_var(self):
        if not hasattr(self, '_review_count_sv'):
            self._review_count_sv = tk.StringVar(value="")
        return self._review_count_sv

    def _toggle_column_menu(self):
        menu = tk.Menu(self, tearoff=0)
        for col_id, col_text, _ in self.REVIEW_COLUMNS:
            menu.add_checkbutton(label=col_text, variable=self._col_visible[col_id],
                                 command=self._refresh_review_table)
        menu.post(self.winfo_pointerx(), self.winfo_pointery())

    def _on_review_double_click(self, event):
        sel = self.review_tree.selection()
        if not sel:
            return
        item = sel[0]
        values = self.review_tree.item(item)["values"]
        col_ids = [c[0] for c in self.REVIEW_COLUMNS]
        data = dict(zip(col_ids, values))

        detail = f"""UID: {data.get('mid', '')}
用户名: {data.get('uname', '')}
签名: {data.get('sign', '')}
认证: {data.get('official', '')}
VIP: {data.get('vip', '')}
粉丝: {data.get('follower', '')}
投稿: {data.get('archive_count', '')}
等级: {data.get('level', '')}
播放量: {data.get('total_view', '')}
f/f比: {data.get('ff_ratio', '')}
封禁: {data.get('spacesta', '')}
关注时间: {data.get('mtime', '')}
保留规则: {data.get('rule_keep', '')}
删除规则: {data.get('rule_delete', '')}
删除分: {data.get('delete_score', '')}
判定: {data.get('verdict', '')}
空间: https://space.bilibili.com/{data.get('mid', '')}"""
        messagebox.showinfo(f"账号详情: {data.get('uname', '')}", detail)

    # ── 排序 ─────────────────────────────────────

    def _sort_by_column(self, col):
        reverse = False
        if hasattr(self, '_sort_col') and self._sort_col == col:
            reverse = not self._sort_reverse
        self._sort_col = col
        self._sort_reverse = reverse

        field = self._COL_FIELD_MAP.get(col)
        if not field:
            return

        def _key(d):
            v = d.get(field)
            if v is None:
                v = "" if field in ("uname", "sign", "rule_keep", "rule_delete", "verdict") else 0
            if isinstance(v, str):
                return v.lower()
            return v or 0

        data = sorted(self._review_data, key=_key, reverse=reverse)
        self._rebuild_tree(data)

    # ── 右键菜单 ─────────────────────────────────

    def _on_tree_right_click(self, event):
        region = self.review_tree.identify_region(event.x, event.y)
        col_str = self.review_tree.identify_column(event.x)
        col_num = int(col_str.replace("#", "")) - 1
        if 0 <= col_num < len(self.REVIEW_COLUMNS):
            col_name = self.REVIEW_COLUMNS[col_num][0]
        else:
            col_name = None

        m = tk.Menu(self.review_tree, tearoff=0)
        if col_name:
            def _asc(c=col_name):
                setattr(self, '_sort_col', '')
                self._sort_by_column(c)
            def _desc(c=col_name):
                setattr(self, '_sort_col', c)
                setattr(self, '_sort_reverse', False)
                self._sort_by_column(c)
                setattr(self, '_sort_reverse', True)
                self._rebuild_tree(
                    sorted(self._review_data,
                           key=lambda d: (d.get(self._COL_FIELD_MAP.get(c, "")) or 0),
                           reverse=True))
            m.add_command(label=f"↑ 按此列正序", command=_asc)
            m.add_command(label=f"↓ 按此列倒序", command=_desc)
        m.add_command(label="📋 复制选中 UID", command=self._copy_selected_uids)
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def _copy_selected_uids(self):
        items = self.review_tree.selection()
        uids = []
        for i in items:
            uids.append(self.review_tree.item(i)["values"][0])
        if uids:
            self.clipboard_clear()
            self.clipboard_append("\n".join(uids))
            self.log(f"已复制 {len(uids)} 个 UID")

    # ── Tab: 取关 ─────────────────────────────────

    def _build_unfollow_tab(self) -> ttk.Frame:
        f = ttk.Frame(self.notebook, padding=10)
        ttk.Label(f, text="执行取关操作", font=("", 12, "bold")).pack(anchor=tk.W)

        info = ttk.Frame(f)
        info.pack(fill=tk.X, pady=10)
        self.unfollow_count_var = tk.StringVar(value="待取关: 0")
        ttk.Label(info, textvariable=self.unfollow_count_var, font=("", 11)).pack(side=tk.LEFT)
        ttk.Button(info, text="📊 刷新计数", command=self._refresh_unfollow_count).pack(side=tk.LEFT, padx=10)

        ttk.Button(f, text="⚠ 执行取关 (不可撤销!)",
                   command=self._execute_unfollow).pack(anchor=tk.W, pady=5)

        self.unfollow_progress = ttk.Progressbar(f, mode="determinate")
        self.unfollow_progress.pack(fill=tk.X, pady=5)

        self.unfollow_log = scrolledtext.ScrolledText(f, height=15, font=("Consolas", 9))
        self.unfollow_log.pack(fill=tk.BOTH, expand=True)

        return f

    # ── 登录逻辑 ──────────────────────────────────

    def _login_qrcode_popup(self):
        import requests
        from PIL import Image, ImageTk

        dlg = tk.Toplevel(self)
        dlg.title("扫码登录")
        dlg.geometry("350x380")
        dlg.transient(self)
        dlg.resizable(False, False)

        status_var = tk.StringVar(value="生成二维码中...")
        ttk.Label(dlg, textvariable=status_var, font=("", 11)).pack(pady=10)

        qr_label = ttk.Label(dlg)
        qr_label.pack(pady=5)

        def _cancel():
            dlg.destroy()

        ttk.Button(dlg, text="取消", command=_cancel).pack(pady=10)

        def _run():
            try:
                session = requests.Session()
                session.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36"
                })
                resp = session.get(
                    "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
                ).json()
                if resp["code"] != 0:
                    raise RuntimeError(f"生成二维码失败: {resp}")
                qr_url = resp["data"]["url"]
                qrcode_key = resp["data"]["qrcode_key"]

                # 本地生成二维码图片
                import qrcode
                qr = qrcode.QRCode(box_size=5, border=2)
                qr.add_data(qr_url)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
                try:
                    img = img.resize((200, 200), Image.Resampling.LANCZOS)
                except (AttributeError, NameError):
                    img = img.resize((200, 200))  # default nearest-neighbor
                photo = ImageTk.PhotoImage(img)

                self.after(0, lambda p=photo: qr_label.configure(image=p))
                # prevent GC
                qr_label._img_ref = photo
                self.after(0, lambda: status_var.set("请使用B站App扫码"))

                # 轮询
                start = time.time()
                while time.time() - start < 180:
                    pr = session.get(
                        "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
                        params={"qrcode_key": qrcode_key}
                    ).json()
                    code = pr.get("data", {}).get("code", -1)
                    if code == 0:
                        cookies = {}
                        for c in session.cookies:
                            cookies[c.name] = c.value
                        from ..auth.login import save_cookies
                        save_cookies(cookies)
                        self.client = BiliClient(cookies)
                        self.after(0, lambda: self._on_login_success())
                        self.after(0, dlg.destroy)
                        return
                    elif code == 86038:
                        self.after(0, lambda: status_var.set("二维码已过期，请关闭重试"))
                        return
                    elif code == 86090:
                        self.after(0, lambda: status_var.set("已扫码，请在App中确认..."))
                    time.sleep(2)
            except Exception as e:
                self.after(0, lambda: self._on_login_fail(str(e)))
                self.after(0, dlg.destroy)

        threading.Thread(target=_run, daemon=True).start()

    def _on_login_success(self):
        uid = self.client.uid if self.client else "?"
        self.status_var.set(f"已登录 (UID: {uid})")
        self.login_status.set("登录成功!")
        self._enable_tabs()
        self.log(f"登录成功! UID: {uid}")

    def _on_login_fail(self, err: str):
        self.login_status.set(f"登录失败: {err}")
        self.log(f"登录失败: {err}")
        messagebox.showerror("登录失败", err)

    # ── 拉取关注 ──────────────────────────────────

    def _fetch_follows(self):
        if not self.client:
            messagebox.showwarning("未登录", "请先登录")
            return
        assert self.client is not None
        client = self.client
        self._start_op()
        self.fetch_progress["value"] = 0
        self.fetch_label.set("拉取中...")
        self.log("开始拉取关注列表...")
        self.update_idletasks()

        def _run():

            def progress(pg, total, count):
                if self._stop_requested:
                    raise RuntimeError("用户中止")
                pct = (pg / total) * 100
                self.after(0, lambda: self.fetch_progress.configure(value=pct))
                self.after(0, lambda: self.fetch_label.set(f"第 {pg}/{total} 页, 已获取 {count}"))

            try:
                follows, total = fetch_all_followings(client, progress_callback=progress)
                self.follows = follows
                count = database.save_follows(follows)
                self.after(0, lambda: self.fetch_label.set(f"完成! 共 {len(follows)}/{total} 条"))
                self.after(0, lambda: self.log(f"关注列表已保存: {count} 条到数据库"))
                self.after(0, self._refresh_review_table)
                self.after(0, self._refresh_stats)
            except RuntimeError as e:
                self.after(0, lambda: self.log(f"操作已停止: {e}"))
            except Exception as e:
                self.after(0, lambda: self.log(f"拉取失败: {e}"))
            finally:
                self.after(0, self._end_op)

        threading.Thread(target=_run, daemon=True).start()

    # ── 规则过滤 ──────────────────────────────────

    def _apply_rules(self):
        if not self.follows:
            self.log("请先拉取关注列表")
            return

        engine = self.rule_engine
        verdicts = []

        for f in self.follows:
            official_type = 0
            ov = f.get("official_verify", {})
            if isinstance(ov, dict):
                official_type = ov.get("type", 0)
            is_vip = False
            vip_data = f.get("vip", {})
            if isinstance(vip_data, dict):
                is_vip = vip_data.get("vipStatus", 0) == 1

            result = engine.evaluate_signature(f, official_type, is_vip)

            # 认证账号自动保护
            if official_type > 0:
                verdict = "protected"
            elif result.keep_score >= result.delete_score:
                verdict = "keep"
            elif result.delete_score >= 40:
                verdict = "delete"
            else:
                verdict = "unreviewed"

            verdicts.append({
                "mid": f["mid"],
                "verdict": verdict,
                "rule_keep": ",".join(result.matched_keep),
                "rule_delete": ",".join(result.matched_delete),
                "keep_score": result.keep_score,
                "delete_score": result.delete_score,
            })

        # 同时应用自定义规则
        self._apply_custom_rules()
        database.save_verdicts(verdicts)
        self._refresh_stats()
        self._refresh_review_table()
        self._refresh_unfollow_count()
        self.log(f"规则已应用: {len(verdicts)} 条判定已保存")

    # ── 特别关注保护 ──────────────────────────────

    def _fetch_special_follows(self):
        """拉取特别关注列表，自动保护"""
        if not self.client:
            messagebox.showwarning("未登录", "请先登录")
            return
        assert self.client is not None
        client = self.client
        self.log("拉取特别关注列表...")

        def _run():
            try:
                resp = client.get("https://api.bilibili.com/x/relation/tag")
                if resp.get("code") != 0:
                    self.after(0, lambda: self.log("获取关注分组失败"))
                    return
                tags = resp.get("data", [])
                special_tagid = -10
                for t in tags:
                    if t.get("tagid") == special_tagid:
                        count = t.get("count", 0)
                        break
                uids = []
                pn = 1
                while True:
                    r = client.get(
                        "https://api.bilibili.com/x/relation/tags",
                        params={"tagid": special_tagid, "pn": pn, "ps": 50}
                    )
                    if r.get("code") != 0:
                        break
                    items = r.get("data", [])
                    if not items:
                        break
                    for u in items:
                        uids.append(u["mid"])
                    pn += 1
                self.special_follow_uids = set(uids)
                conn = database.get_conn()
                for uid in uids:
                    conn.execute(
                        "INSERT OR REPLACE INTO verdicts (mid, verdict, rule_keep, keep_score) "
                        "VALUES (?, 'protected', '特别关注', 999)",
                        (uid,)
                    )
                conn.commit()
                conn.close()
                self.after(0, lambda: self.log(f"特别关注: {len(uids)} 个已自动保护 ⭐"))
                self.after(0, self._refresh_review_table)
            except Exception as e:
                self.after(0, lambda: self.log(f"拉取特别关注失败: {e}"))

        threading.Thread(target=_run, daemon=True).start()

    def _deep_probe(self):
        if not self.client:
            messagebox.showwarning("未登录", "请先登录")
            return
        assert self.client is not None
        client = self.client
        self._start_op()
        self.filter_progress["value"] = 0

        # 获取待探测 UID
        uids = database.get_follow_uids()
        if not uids:
            conn = database.get_conn()
            rows = conn.execute("SELECT mid FROM follows").fetchall()
            conn.close()
            uids = [r["mid"] for r in rows]

        uids = [str(u) for u in uids]
        self.filter_label.set(f"探测中: 0/{len(uids)}")
        self.log(f"开始深度探测 {len(uids)} 个账号 (批量5, 间隔3s)...")
        self.update_idletasks()

        def _run():
            def progress(done, total):
                if self._stop_requested:
                    raise RuntimeError("用户中止")
                pct = (done / total) * 100
                self.after(0, lambda: self.filter_progress.configure(value=pct))
                self.after(0, lambda: self.filter_label.set(f"探测中: {done}/{total}"))

            try:
                results = batch_probe(client, uids, concurrency=5, batch_delay=3.0,
                                      progress_callback=progress)
                self.probes = results
                database.save_probes(results)

                # 应用探测规则
                engine = self.rule_engine
                probe_verdicts = []
                for p in results:
                    r = engine.evaluate_probe(p)
                    conn = database.get_conn()
                    row = conn.execute(
                        "SELECT keep_score, delete_score FROM verdicts WHERE mid = ?",
                        (p["uid"],)
                    ).fetchone()
                    conn.close()

                    old_keep = row["keep_score"] if row else 0
                    old_delete = row["delete_score"] if row else 0
                    total_keep = old_keep + r.keep_score
                    total_delete = old_delete + r.delete_score
                    v = "unreviewed"
                    if total_delete >= 150 and total_keep < 100:
                        v = "delete"
                    elif total_keep >= total_delete:
                        v = "keep"

                    probe_verdicts.append({
                        "mid": p["uid"],
                        "verdict": v,
                        "rule_keep": ",".join(r.matched_keep),
                        "rule_delete": ",".join(r.matched_delete),
                        "rule_probe": ",".join(r.matched_probe),
                        "keep_score": total_keep,
                        "delete_score": total_delete,
                    })

                database.save_verdicts(probe_verdicts)
                self.after(0, lambda: self.filter_label.set(f"探测完成: {len(results)} 条"))
                self.after(0, lambda: self.log(
                    f"深度探测完成: {len(results)} 条, 已更新判定"))
                self._refresh_stats()
                self.after(0, self._refresh_review_table)
            except RuntimeError as e:
                self.after(0, lambda: self.log(f"操作已停止: {e}"))
            except Exception as e:
                self.after(0, lambda: self.log(f"探测失败: {e}"))
            finally:
                self.after(0, self._end_op)

        threading.Thread(target=_run, daemon=True).start()

    def _refresh_stats(self):
        stats = database.get_stats()
        self.log(f"统计: 总关注 {stats.get('total_follows', 0)}, "
                 f"保留 {stats.get('verdict_keep', 0)}, "
                 f"删除 {stats.get('verdict_delete', 0)}, "
                 f"待审 {stats.get('verdict_unreviewed', 0)}")

    # ── 审查 ─────────────────────────────────────

    def _refresh_review_table(self):
        verdict_filter = self.review_filter.get()
        if verdict_filter == "all":
            verdict_filter = None
        try:
            data = database.get_all_with_verdicts(verdict_filter)
        except Exception:
            return
        self._review_data = data
        self._search_review_table()

    def _search_review_table(self):
        text = self.search_var.get().lower().strip()
        if text:
            col_ids = [c[0] for c in self.REVIEW_COLUMNS]
            filtered = []
            for d in self._review_data:
                match_str = " ".join(
                    str(d.get(self._COL_FIELD_MAP.get(c, c), "") or "")
                    for c in col_ids
                ).lower()
                if text in match_str:
                    filtered.append(d)
            data = filtered
        else:
            data = self._review_data
        self._rebuild_tree(data)

    def _rebuild_tree(self, data):
        for row in self.review_tree.get_children():
            self.review_tree.delete(row)

        col_ids = [c[0] for c in self.REVIEW_COLUMNS]

        for d in data:
            official = (d.get("official_verify_type") or 0) > 0
            vip_status = (d.get("vip_status") or 0)
            vip_type = d.get("vip_type") or 0
            spacesta = d.get("spacesta")
            spacesta_str = "封禁" if spacesta == -2 else ("正常" if spacesta == 0 else "?")
            lv = d.get("level") or -1
            ac = d.get("archive_count") or -1
            ff = d.get("ff_ratio") or 0
            follower = d.get("probe_follower") or -1
            total_view = d.get("total_view") or -1

            mtime_ts = d.get("mtime") or 0
            if mtime_ts > 0:
                mtime_str = time.strftime("%Y-%m-%d", time.localtime(mtime_ts))
            else:
                mtime_str = ""

            verdict = d.get("verdict") or "unreviewed"
            is_special = d["mid"] in self.special_follow_uids
            rule_keep = d.get("rule_keep") or ""
            if verdict == "protected":
                verdict_display = "⭐特别关注" if is_special else "🔒保护"
            else:
                verdict_display = {"keep": "保留", "delete": "删除"}.get(verdict, "待审")

            values_map = {
                "mid": str(d["mid"]),
                "uname": d.get("uname") or "",
                "sign": (d.get("sign") or "")[:40],
                "official": "✓" if official else "",
                "vip": {1: "月度", 2: "年度"}.get(vip_type, "") if vip_status else "",
                "follower": str(follower) if follower >= 0 else "",
                "archive_count": str(ac) if ac >= 0 else "",
                "level": str(lv) if lv >= 0 else "",
                "total_view": str(total_view) if total_view >= 0 else "",
                "ff_ratio": f"{ff:.1f}" if ff >= 1.5 else "",
                "spacesta": spacesta_str,
                "mtime": mtime_str,
                "rule_keep": (d.get("rule_keep") or "")[:30],
                "rule_delete": (d.get("rule_delete") or "")[:30],
                "delete_score": str(d.get("delete_score") or 0),
                "verdict": verdict_display,
            }

            values = tuple(values_map.get(c, "") for c in col_ids)
            self.review_tree.insert("", tk.END, values=values)

        # 应用列可见性
        visible_cols = [c for c in col_ids if self._col_visible.get(c) and self._col_visible[c].get()]
        self.review_tree.configure(displaycolumns=visible_cols)

        self._review_count_var().set(f"共 {len(data)} 条")

    def _set_verdict(self, verdict: str):
        sel = self.review_tree.selection()
        if not sel:
            return
        rejected = []
        for item in sel:
            mid = self.review_tree.item(item)["values"][0]
            # 查找此行的当前判定
            conn = database.get_conn()
            row = conn.execute("SELECT verdict FROM verdicts WHERE mid = ?", (mid,)).fetchone()
            conn.close()
            current = row["verdict"] if row else "unreviewed"
            if current == "protected" and verdict == "delete":
                rejected.append(
                    self.review_tree.item(item)["values"][1]  # uname
                )
                continue
            database.save_verdicts([{"mid": mid, "verdict": verdict}])
        if rejected:
            messagebox.showwarning("保护中", f"以下账号已锁定保护，不可标记为删除:\n" + "\n".join(rejected))
        self._refresh_review_table()
        self._refresh_unfollow_count()
        self.log(f"已标记 {len(sel) - len(rejected)} 条 → {verdict}" + (
            f" ({len(rejected)} 条被保护拒绝)" if rejected else ""))

    def _save_all_verdicts(self):
        database.save_verdicts([])
        self.log("判定已持久化")

    # ── 自定义规则对话框 ──────────────────────────

    def _get_custom_rules_path(self):
        from ..utils.helpers import get_data_dir
        return get_data_dir() / "custom_rules.toml"

    def _load_custom_rules(self) -> list[dict]:
        p = self._get_custom_rules_path()
        if not p.exists():
            return []
        import tomllib as _tl
        try:
            with open(p, "rb") as f:
                data = _tl.load(f)
            return data.get("rule", [])
        except Exception:
            return []

    def _save_custom_rules(self, rules: list[dict]):
        p = self._get_custom_rules_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        import tomllib as _tl  # noqa (just for the file; write manually)
        lines = ["# 自定义删除规则 — 格式: [[rule]]\n"]
        for r in rules:
            lines.append("[[rule]]\n")
            lines.append(f'name = "{r["name"]}"\n')
            lines.append(f'field = "{r["field"]}"\n')
            lines.append(f'pattern = """{r["pattern"]}"""\n')
            lines.append(f'score = {r["score"]}\n\n')
        p.write_text("".join(lines), encoding="utf-8")

    def _apply_custom_rules(self):
        rules = self._load_custom_rules()
        if not rules:
            return
        import re as _re
        conn = database.get_conn()
        follows = conn.execute("SELECT mid, uname, sign FROM follows").fetchall()
        conn.close()
        for frow in follows:
            mid = frow["mid"]
            uname = frow["uname"] or ""
            sign = frow["sign"] or ""
            for r in rules:
                field = r.get("field", "both")
                pat = r.get("pattern", "")
                name = r.get("name", "")
                score = r.get("score", 20)
                if not pat:
                    continue
                text = ""
                if field == "uname":
                    text = uname
                elif field == "sign":
                    text = sign
                else:
                    text = f"{uname} {sign}"
                try:
                    if _re.search(pat, text, _re.IGNORECASE):
                        conn2 = database.get_conn()
                        existing = conn2.execute(
                            "SELECT delete_score, rule_delete FROM verdicts WHERE mid = ?",
                            (mid,)
                        ).fetchone()
                        old_score = existing["delete_score"] or 0 if existing else 0
                        old_rules = existing["rule_delete"] or "" if existing else ""
                        new_rules = old_rules + ("," if old_rules else "") + f"[自定义]{name}"
                        conn2.execute(
                            "INSERT OR REPLACE INTO verdicts (mid, verdict, delete_score, rule_delete, keep_score) "
                            "VALUES (?, 'delete', ?, ?, 0)",
                            (mid, old_score + score, new_rules)
                        )
                        conn2.commit()
                        conn2.close()
                except _re.error:
                    self.log(f"自定义规则正则错误: {name} — {pat}")

    def _open_custom_rules_dialog(self):
        rules = self._load_custom_rules()
        dlg = tk.Toplevel(self)
        dlg.title("自定义规则")
        dlg.geometry("700x400")
        dlg.transient(self)

        tree_frame = ttk.Frame(dlg)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        cols = ("name", "field", "pattern", "score")
        tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
        tree.heading("name", text="名称")
        tree.heading("field", text="匹配字段")
        tree.heading("pattern", text="正则")
        tree.heading("score", text="分数")
        tree.column("name", width=120)
        tree.column("field", width=80)
        tree.column("pattern", width=300)
        tree.column("score", width=60)
        tree.pack(fill=tk.BOTH, expand=True)

        def _refresh():
            for row in tree.get_children():
                tree.delete(row)
            for r in self._load_custom_rules():
                tree.insert("", tk.END, values=(r["name"], r["field"], r["pattern"], r["score"]))

        _refresh()

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)

        def _add():
            add_dlg = tk.Toplevel(dlg)
            add_dlg.title("添加规则")
            add_dlg.geometry("400x250")
            add_dlg.transient(dlg)
            ttk.Label(add_dlg, text="名称:").pack(anchor=tk.W, padx=10, pady=(10, 0))
            name_var = tk.StringVar()
            ttk.Entry(add_dlg, textvariable=name_var, width=40).pack(padx=10)
            ttk.Label(add_dlg, text="匹配字段:").pack(anchor=tk.W, padx=10, pady=(10, 0))
            field_var = tk.StringVar(value="both")
            ttk.Combobox(add_dlg, textvariable=field_var, values=["uname", "sign", "both"], width=10).pack(anchor=tk.W, padx=10)
            ttk.Label(add_dlg, text="正则表达式:").pack(anchor=tk.W, padx=10, pady=(10, 0))
            pat_var = tk.StringVar()
            ttk.Entry(add_dlg, textvariable=pat_var, width=40).pack(padx=10)
            ttk.Label(add_dlg, text="分数 (0-200):").pack(anchor=tk.W, padx=10, pady=(10, 0))
            score_var = tk.StringVar(value="30")
            ttk.Entry(add_dlg, textvariable=score_var, width=10).pack(anchor=tk.W, padx=10)

            def _save():
                name = name_var.get().strip()
                pat = pat_var.get().strip()
                if not name or not pat:
                    return
                rules = self._load_custom_rules()
                rules.append({
                    "name": name, "field": field_var.get(),
                    "pattern": pat, "score": int(score_var.get())
                })
                self._save_custom_rules(rules)
                add_dlg.destroy()
                _refresh()
            ttk.Button(add_dlg, text="保存", command=_save).pack(pady=10)

        ttk.Button(btn_frame, text="➕ 添加", command=_add).pack(side=tk.LEFT, padx=3)

        def _delete():
            sel = tree.selection()
            if not sel:
                return
            idx = tree.index(sel[0])
            rules = self._load_custom_rules()
            if 0 <= idx < len(rules):
                rules.pop(idx)
                self._save_custom_rules(rules)
                _refresh()
        ttk.Button(btn_frame, text="🗑 删除", command=_delete).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="关闭", command=dlg.destroy).pack(side=tk.RIGHT, padx=3)

    # ── 自定义API对话框 ──────────────────────────

    def _get_custom_api_path(self):
        from ..utils.helpers import get_data_dir
        return get_data_dir() / "custom_apis.toml"

    def _open_custom_api_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("自定义API探测")
        dlg.geometry("600x400")
        dlg.transient(self)

        ttk.Label(dlg, text="添加自定义 API 端点用于批量探测，{mid} 会被替换为 UID", padding=10).pack()

        tree_frame = ttk.Frame(dlg)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10)

        cols = ("name", "url", "method", "extract")
        tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
        tree.heading("name", text="名称")
        tree.heading("url", text="URL (用{mid})")
        tree.heading("method", text="方法")
        tree.heading("extract", text="提取字段")
        tree.column("name", width=100)
        tree.column("url", width=250)
        tree.column("method", width=60)
        tree.column("extract", width=100)
        tree.pack(fill=tk.BOTH, expand=True)

        def _refresh():
            for row in tree.get_children():
                tree.delete(row)
            p = self._get_custom_api_path()
            if p.exists():
                import tomllib as _tl
                try:
                    with open(p, "rb") as f:
                        data = _tl.load(f)
                    for a in data.get("api", []):
                        tree.insert("", tk.END, values=(
                            a["name"], a["url"], a.get("method", "GET"),
                            a.get("extract_field", "")
                        ))
                except Exception:
                    pass

        _refresh()

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)

        def _add():
            add_dlg = tk.Toplevel(dlg)
            add_dlg.title("添加API")
            add_dlg.geometry("450x250")
            add_dlg.transient(dlg)
            ttk.Label(add_dlg, text="名称:").pack(anchor=tk.W, padx=10)
            name_var = tk.StringVar()
            ttk.Entry(add_dlg, textvariable=name_var, width=40).pack(padx=10)
            ttk.Label(add_dlg, text="URL ({mid} 替换):").pack(anchor=tk.W, padx=10, pady=(5, 0))
            url_var = tk.StringVar()
            ttk.Entry(add_dlg, textvariable=url_var, width=40).pack(padx=10)
            ttk.Label(add_dlg, text="提取字段 (如 data.level):").pack(anchor=tk.W, padx=10, pady=(5, 0))
            extract_var = tk.StringVar()
            ttk.Entry(add_dlg, textvariable=extract_var, width=40).pack(padx=10)
            ttk.Label(add_dlg, text="请求方法:").pack(anchor=tk.W, padx=10, pady=(5, 0))
            method_var = tk.StringVar(value="GET")
            ttk.Combobox(add_dlg, textvariable=method_var, values=["GET", "POST"], width=10).pack(anchor=tk.W, padx=10)

            def _save():
                name = name_var.get().strip()
                url = url_var.get().strip()
                if not name or not url:
                    return
                p = self._get_custom_api_path()
                p.parent.mkdir(parents=True, exist_ok=True)
                import tomllib as _tl
                apis = []
                if p.exists():
                    try:
                        with open(p, "rb") as f:
                            apis = _tl.load(f).get("api", [])
                    except Exception:
                        pass
                apis.append({
                    "name": name, "url": url, "method": method_var.get(),
                    "extract_field": extract_var.get()
                })
                lines = ["# 自定义 API 端点\n"]
                for a in apis:
                    lines.append("[[api]]\n")
                    lines.append(f'name = "{a["name"]}"\n')
                    lines.append(f'url = """{a["url"]}"""\n')
                    lines.append(f'method = "{a.get("method", "GET")}"\n')
                    lines.append(f'extract_field = "{a.get("extract_field", "")}"\n\n')
                p.write_text("".join(lines), encoding="utf-8")
                add_dlg.destroy()
                _refresh()
            ttk.Button(add_dlg, text="保存", command=_save).pack(pady=10)

        ttk.Button(btn_frame, text="➕ 添加", command=_add).pack(side=tk.LEFT, padx=3)

        def _delete():
            sel = tree.selection()
            if not sel:
                return
            idx = tree.index(sel[0])
            p = self._get_custom_api_path()
            if p.exists():
                import tomllib as _tl
                try:
                    with open(p, "rb") as f:
                        apis = _tl.load(f).get("api", [])
                    if 0 <= idx < len(apis):
                        apis.pop(idx)
                        lines = ["# 自定义 API 端点\n"]
                        for a in apis:
                            lines.append("[[api]]\n")
                            lines.append(f'name = "{a["name"]}"\n')
                            lines.append(f'url = """{a["url"]}"""\n')
                            lines.append(f'method = "{a.get("method", "GET")}"\n')
                            lines.append(f'extract_field = "{a.get("extract_field", "")}"\n\n')
                        p.write_text("".join(lines), encoding="utf-8")
                except Exception:
                    pass
            _refresh()
        ttk.Button(btn_frame, text="🗑 删除", command=_delete).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="关闭", command=dlg.destroy).pack(side=tk.RIGHT, padx=3)

    # ── 取关 ─────────────────────────────────────

    def _refresh_unfollow_count(self):
        try:
            conn = database.get_conn()
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM verdicts WHERE verdict = 'delete'"
            ).fetchone()
            conn.close()
            count = row["cnt"] if row else 0
            self.unfollow_count_var.set(f"待取关: {count}")
        except Exception:
            self.unfollow_count_var.set("统计失败")

    def _execute_unfollow(self):
        if not self.client:
            messagebox.showwarning("未登录", "请先登录")
            return
        assert self.client is not None
        client = self.client

        conn = database.get_conn()
        rows = conn.execute(
            "SELECT f.mid, f.uname FROM follows f "
            "JOIN verdicts v ON f.mid = v.mid WHERE v.verdict = 'delete'"
        ).fetchall()
        conn.close()

        if not rows:
            messagebox.showinfo("提示", "没有标记为删除的账号")
            return

        ids = [f"{r['mid']} - {r['uname']}" for r in rows]
        count = len(rows)

        # ── 1级: 数量确认 ──
        if not messagebox.askyesno(
            "取关确认 (1/3)",
            f"共 {count} 个账号标记为待取关。\n\n"
            "下一步将展示 UID 与用户名列表，\n确认查看？"
        ):
            return

        # ── 2级: 名单确认 ──
        confirm_flag = [False]

        def _confirm():
            confirm_flag[0] = True
            list_dlg.destroy()

        def _cancel():
            list_dlg.destroy()

        list_dlg = tk.Toplevel(self)
        list_dlg.title(f"取关确认 (2/3) — {count} 个账号")
        list_dlg.geometry("500x400")
        list_dlg.transient(self)

        btn_f = ttk.Frame(list_dlg)
        btn_f.pack(fill=tk.X, padx=10, pady=(10, 5), side=tk.BOTTOM)
        ttk.Button(btn_f, text="确认取关这些账号", command=_confirm).pack(side=tk.RIGHT, padx=3)
        ttk.Button(btn_f, text="取消", command=_cancel).pack(side=tk.RIGHT, padx=3)

        st = scrolledtext.ScrolledText(list_dlg, font=("Consolas", 10))
        st.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))
        for line in ids:
            st.insert(tk.END, line + "\n")
        st.configure(state=tk.DISABLED)

        self.wait_window(list_dlg)
        if not confirm_flag[0]:
            return

        # ── 3级: 不可恢复警告 ──
        input_dlg = tk.Toplevel(self)
        input_dlg.title("取关确认 (3/3) — 最终警告")
        input_dlg.geometry("420x200")
        input_dlg.transient(self)

        ttk.Label(input_dlg, text="⚠ 此操作不可恢复！", font=("", 12, "bold"), foreground="red").pack(pady=10)
        ttk.Label(input_dlg, text=f"即将永久取消关注 {count} 个账号。\n请在下方输入 DELETE 确认操作：").pack()

        input_var = tk.StringVar()
        ttk.Entry(input_dlg, textvariable=input_var, width=20, font=("", 11)).pack(pady=10)

        final_ok = [False]

        def _final():
            if input_var.get().strip() == "DELETE":
                final_ok[0] = True
                input_dlg.destroy()
            else:
                messagebox.showwarning("输入错误", "请输入 DELETE 确认", parent=input_dlg)

        ttk.Button(input_dlg, text="确认取关", command=_final).pack()
        ttk.Button(input_dlg, text="取消", command=input_dlg.destroy).pack(pady=5)

        self.wait_window(input_dlg)
        if not final_ok[0]:
            self.log("取关已取消")
            return

        # ── 执行 ──
        uids = [str(r["mid"]) for r in rows]
        self.unfollow_log.insert(tk.END, f"开始取关 {len(uids)} 个账号...\n")

        def _run():
            def progress(done, total, ok):
                pct = (done / total) * 100
                self.after(0, lambda: self.unfollow_progress.configure(value=pct))
                self.after(0, lambda: self.unfollow_log.insert(
                    tk.END,
                    f"  [{done}/{total}] 成功: {ok}\n"
                ))
                self.after(0, lambda: self.unfollow_log.see(tk.END))

            try:
                ok, fail = batch_unfollow(client, uids, interval=3.0,
                                          progress_callback=progress)
                self.after(0, lambda: self.log(f"取关完成: {ok} 成功, {fail} 失败"))
                # 取关后标记为已处理
                conn2 = database.get_conn()
                conn2.execute(
                    "DELETE FROM verdicts WHERE verdict = 'delete'"
                )
                conn2.commit()
                conn2.close()
                self._refresh_unfollow_count()
            except Exception as e:
                self.after(0, lambda: self.log(f"取关异常: {e}"))

        threading.Thread(target=_run, daemon=True).start()
