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
        self.title("Bilibili 关注管理器 v0.1")
        self.geometry("1200x750")
        self.minsize(900, 600)

        self.client: BiliClient | None = None
        self.rule_engine = RuleEngine()
        self.follows: list[dict] = []
        self.probes: list[dict] = []

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

    # ── UI 构建 ───────────────────────────────────

    def _build_ui(self):
        # 状态栏
        self.status_var = tk.StringVar(value="未登录")
        status_bar = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W, padding=4)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

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

        ttk.Button(login_frame, text="🔑 扫码登录 (终端ASCII QR)", command=self._login_terminal).pack(
            side=tk.LEFT, padx=5)
        ttk.Button(login_frame, text="🔑 扫码登录 (浏览器)", command=self._login_browser).pack(
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
        ttk.Button(btns, text="🔬 深层探测可疑账号", command=self._deep_probe).pack(side=tk.LEFT, padx=5)
        ttk.Button(btns, text="📊 刷新统计", command=self._refresh_stats).pack(side=tk.LEFT, padx=5)

        self.filter_progress = ttk.Progressbar(f, mode="determinate")
        self.filter_progress.pack(fill=tk.X, pady=5)

        self.filter_label = tk.StringVar(value="准备就绪")
        ttk.Label(f, textvariable=self.filter_label).pack(anchor=tk.W)

        return f

    # ── Tab: 审查 ─────────────────────────────────

    REVIEW_COLUMNS = [
        ("mid", "UID", 90),
        ("uname", "用户名", 100),
        ("sign", "签名", 180),
        ("official", "认证", 60),
        ("vip", "VIP", 40),
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
        ttk.Button(toolbar, text="列显示", command=self._toggle_column_menu).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="🔄 刷新", command=self._refresh_review_table).pack(side=tk.RIGHT, padx=5)
        ttk.Label(toolbar, textvariable=self._review_count_var()).pack(side=tk.RIGHT, padx=5)

        # Treeview
        tree_frame = ttk.Frame(f)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        col_ids = [c[0] for c in self.REVIEW_COLUMNS]
        self.review_tree = ttk.Treeview(tree_frame, columns=col_ids, show="headings", selectmode="extended")
        for col_id, col_text, col_width in self.REVIEW_COLUMNS:
            self.review_tree.heading(col_id, text=col_text)
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

        # 判定按钮
        action_frame = ttk.Frame(f)
        action_frame.pack(fill=tk.X, pady=5)
        ttk.Button(action_frame, text="🔴 标记删除", command=lambda: self._set_verdict("delete")).pack(side=tk.LEFT, padx=3)
        ttk.Button(action_frame, text="🟢 标记保留", command=lambda: self._set_verdict("keep")).pack(side=tk.LEFT, padx=3)
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

    def _login_terminal(self):
        self.log("终端展示二维码, 请查看控制台窗口扫码...")
        def _run():
            try:
                cookies, _ = login_qrcode(as_image=False, poll_timeout=180)
                self.client = BiliClient(cookies)
                self.after(0, lambda: self._on_login_success())
            except Exception as e:
                self.after(0, lambda: self._on_login_fail(str(e)))
        threading.Thread(target=_run, daemon=True).start()

    def _login_browser(self):
        import webbrowser
        self.log("终端的扫码链接已复制, 同时尝试打开浏览器...")
        def _run():
            try:
                import requests
                session = requests.Session()
                session.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36"
                })
                resp = session.get(
                    "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
                ).json()
                if resp["code"] == 0:
                    qr_url = resp["data"]["url"]
                    qrcode_key = resp["data"]["qrcode_key"]
                    webbrowser.open(qr_url)
                    self.log(f"浏览器已打开, 或手动访问: {qr_url}")
                    self.log("扫码后等待确认...")

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
                            return
                        elif code == 86038:
                            raise RuntimeError("二维码已过期")
                        time.sleep(2)
                else:
                    raise RuntimeError(f"生成二维码失败: {resp}")
            except Exception as e:
                self.after(0, lambda: self._on_login_fail(str(e)))
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

        def _run():
            self.fetch_progress["value"] = 0
            self.fetch_label.set("拉取中...")
            self.log("开始拉取关注列表...")

            def progress(pg, total, count):
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
            except Exception as e:
                self.after(0, lambda: self.log(f"拉取失败: {e}"))

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

            # 判定
            if result.keep_score >= result.delete_score:
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

        database.save_verdicts(verdicts)
        self._refresh_stats()
        self._refresh_review_table()
        self.log(f"规则已应用: {len(verdicts)} 条判定已保存")

    def _deep_probe(self):
        if not self.client:
            messagebox.showwarning("未登录", "请先登录")
            return
        assert self.client is not None
        client = self.client

        # 获取待探测 UID (unreviewed + delete)
        uids = database.get_follow_uids()
        if not uids:
            # 从数据库取所有关注的 UID
            conn = database.get_conn()
            rows = conn.execute("SELECT mid FROM follows").fetchall()
            conn.close()
            uids = [r["mid"] for r in rows]

        uids = [str(u) for u in uids]
        self.log(f"开始深度探测 {len(uids)} 个账号...")

        def _run():
            def progress(done, total):
                pct = (done / total) * 100
                self.after(0, lambda: self.filter_progress.configure(value=pct))
                self.after(0, lambda: self.filter_label.set(f"探测中: {done}/{total}"))

            try:
                results = batch_probe(client, uids, concurrency=8, batch_delay=1.5,
                                      progress_callback=progress)
                self.probes = results
                database.save_probes(results)

                # 应用探测规则
                engine = self.rule_engine
                probe_verdicts = []
                for p in results:
                    r = engine.evaluate_probe(p)
                    # 获取已有签名判定
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

                    if total_delete >= 150 and total_keep < 100:
                        v = "delete"
                    elif total_keep >= total_delete:
                        v = "keep"
                    else:
                        v = "unreviewed"

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
            except Exception as e:
                self.after(0, lambda: self.log(f"探测失败: {e}"))

        threading.Thread(target=_run, daemon=True).start()

    def _refresh_stats(self):
        stats = database.get_stats()
        self.log(f"统计: 总关注 {stats.get('total_follows', 0)}, "
                 f"保留 {stats.get('verdict_keep', 0)}, "
                 f"删除 {stats.get('verdict_delete', 0)}, "
                 f"待审 {stats.get('verdict_unreviewed', 0)}")

    # ── 审查 ─────────────────────────────────────

    def _refresh_review_table(self):
        for row in self.review_tree.get_children():
            self.review_tree.delete(row)

        verdict_filter = self.review_filter.get()
        if verdict_filter == "all":
            verdict_filter = None

        try:
            data = database.get_all_with_verdicts(verdict_filter)
        except Exception:
            return

        col_ids = [c[0] for c in self.REVIEW_COLUMNS]

        for d in data:
            official = (d.get("official_verify_type") or 0) > 0
            vip = (d.get("vip_status") or 0) == 1
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
            verdict_display = {"keep": "保留", "delete": "删除"}.get(verdict, "待审")

            values_map = {
                "mid": str(d["mid"]),
                "uname": d.get("uname") or "",
                "sign": (d.get("sign") or "")[:40],
                "official": "✓" if official else "",
                "vip": "✓" if vip else "",
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
        self.log(f"审查表格已刷新: {len(data)} 条")

    def _set_verdict(self, verdict: str):
        sel = self.review_tree.selection()
        if not sel:
            return
        for item in sel:
            mid = self.review_tree.item(item)["values"][0]
            database.save_verdicts([{"mid": mid, "verdict": verdict}])
        self._refresh_review_table()
        self.log(f"已标记 {len(sel)} 条 → {verdict}")

    def _save_all_verdicts(self):
        database.save_verdicts([])  # trigger save (already saved per-item)
        self.log("判定已持久化")

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
            "SELECT mid, uname FROM follows f "
            "JOIN verdicts v ON f.mid = v.mid WHERE v.verdict = 'delete'"
        ).fetchall()
        conn.close()

        if not rows:
            messagebox.showinfo("提示", "没有标记为删除的账号")
            return

        count = len(rows)
        if not messagebox.askyesno(
            "确认取关",
            f"即将取关 {count} 个账号, 此操作不可撤销!\n\n"
            "确定要继续吗?"
        ):
            return

        uids = [str(r["mid"]) for r in rows]
        self.unfollow_log.insert(tk.END, f"开始取关 {len(uids)} 个账号...\n")

        def _run():
            def progress(done, total, ok):
                pct = (done / total) * 100
                self.after(0, lambda: self.unfollow_progress.configure(value=pct))
                self.after(0, lambda: self.unfollow_log.insert(
                    tk.END,
                    f"  [{done}/{total}] {'✓' if done == ok else '✗'} "
                    f"成功: {ok}/{done}\n"
                ))
                self.after(0, lambda: self.unfollow_log.see(tk.END))

            try:
                ok, fail = batch_unfollow(client, uids, interval=3.0,
                                          progress_callback=progress)
                self.after(0, lambda: self.log(f"取关完成: {ok} 成功, {fail} 失败"))
                self._refresh_unfollow_count()
            except Exception as e:
                self.after(0, lambda: self.log(f"取关异常: {e}"))

        threading.Thread(target=_run, daemon=True).start()
