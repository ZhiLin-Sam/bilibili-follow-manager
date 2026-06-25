"""拉取页面 — 扫码登录 + 拉取关注列表"""

import json
import threading
import tkinter as tk
import tkinter.ttk as ttk
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageTk
import qrcode

from .base import BasePage
from .. import pages as page_registry
from ..auth.login import (
    login_qrcode, load_cookies, save_cookies, get_qr_image, QR_GENERATE_URL,
)
from ..api.client import BiliClient
from ..api.following import fetch_all_followings
from ..db import database
from ..theme import BG0, BG1, BG2, FG0, FG1, ACCENT, GREEN, RED

import requests


@page_registry.register_page
class FetchPage(BasePage):
    page_id = "fetch"
    title = "拉取"
    order = 1

    def _build_icon(self):
        from ..app import _icon_fetch, _make_icon
        return _make_icon(_icon_fetch)

    def _build(self, parent: ttk.Frame) -> None:
        super()._build(parent)
        f = parent

        # 标题
        ttk.Label(f, text="登录 & 拉取关注列表", style="Header.TLabel").pack(anchor="w", pady=(0, 5))

        # 状态显示
        self.status_var = tk.StringVar(value="未登录")
        ttk.Label(f, textvariable=self.status_var, style="Subtitle.TLabel").pack(anchor="w", pady=(0, 10))

        # ── 登录按钮组 ──
        btn_row = ttk.Frame(f)
        btn_row.pack(fill=tk.X, pady=(0, 10))

        self.login_btn = ttk.Button(btn_row, text="扫码登录", style="Accent.TButton",
                                     command=self._start_login)
        self.login_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.cookie_btn = ttk.Button(btn_row, text="加载缓存 Cookie",
                                      command=self._load_cached_cookies)
        self.cookie_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.logout_btn = ttk.Button(btn_row, text="注销", command=self._logout)
        self.logout_btn.pack(side=tk.LEFT)

        # ── 拉取按钮组 ──
        fetch_row = ttk.Frame(f)
        fetch_row.pack(fill=tk.X, pady=(10, 5))

        ttk.Button(fetch_row, text="拉取全部关注", style="Accent.TButton",
                   command=self._start_fetch).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(fetch_row, text="拉取特别关注",
                   command=self._start_special_fetch).pack(side=tk.LEFT, padx=(0, 8))

        self._btn_stop = ttk.Button(fetch_row, text="⏹ 停止", command=self._stop_op,
                                     state=tk.DISABLED)
        self._btn_stop.pack(side=tk.LEFT, padx=(0, 8))

        self._op_active = False
        self._stop_requested = False

        # ── 进度条 ──
        self.progress = ttk.Progressbar(f, mode="determinate")
        self.progress.pack(fill=tk.X, pady=(5, 5))
        self.progress_label = ttk.Label(f, text="", style="Subtitle.TLabel")
        self.progress_label.pack(anchor="w")

        # ── 统计 ──
        self.stats_var = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.stats_var, style="Mono.TLabel").pack(anchor="w", pady=(10, 0))

        # ── 刷新统计 ──
        self._refresh_stats()

    # ── 操作安全 ──

    def _start_op(self):
        self._op_active = True
        self._stop_requested = False
        self._btn_stop.configure(state=tk.NORMAL)

    def _end_op(self):
        self._op_active = False
        self._stop_requested = False
        self._btn_stop.configure(state=tk.DISABLED)

    def _stop_op(self):
        self._stop_requested = True
        self.log("正在停止...")

    # ── 登录 ──

    def _start_login(self):
        """弹出二维码登录窗口"""
        self.log("正在生成二维码...")
        self._qr_popup()

    def _qr_popup(self):
        dlg = tk.Toplevel(self.app)
        dlg.title("扫码登录")
        dlg.geometry("320x380")
        dlg.transient(self.app)
        dlg.configure(bg=BG0)
        dlg.resizable(False, False)

        status = tk.StringVar(value="正在生成二维码...")
        ttk.Label(dlg, textvariable=status, style="Subtitle.TLabel").pack(pady=(15, 10))

        qr_label = ttk.Label(dlg)
        qr_label.pack(pady=5)

        # 获取二维码 URL
        HEADERS = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
        }

        def _poll():
            try:
                session = requests.Session()
                session.headers.update(HEADERS)
                resp = session.get(QR_GENERATE_URL).json()
                if resp.get("code") != 0:
                    self.app.ui_call(lambda: status.set(f"生成失败: {resp}"))
                    return
                qrcode_key = resp["data"]["qrcode_key"]
                qr_url = resp["data"]["url"]

                # 生成 QR 图片
                qr = qrcode.QRCode(box_size=5, border=2)
                qr.add_data(qr_url)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
                buf = BytesIO()
                img.save(buf, "PNG")
                buf.seek(0)

                photo = ImageTk.PhotoImage(Image.open(buf))
                self.app.ui_call(lambda: [
                    qr_label.configure(image=photo),
                    setattr(qr_label, '_img', photo),
                    status.set("请使用哔哩哔哩APP扫码")
                ])

                # 轮询
                import time
                start = time.time()
                while time.time() - start < 180:
                    if self._stop_requested:
                        self.app.ui_call(lambda: status.set("已取消"))
                        return
                    poll_resp = session.get(
                        "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
                        params={"qrcode_key": qrcode_key}
                    ).json()
                    code = poll_resp.get("data", {}).get("code", -1)
                    if code == 0:
                        # 成功
                        cookies = {}
                        for c in session.cookies:
                            cookies[c.name] = c.value
                        if "DedeUserID" in cookies:
                            try:
                                cookies["DedeUserID"] = str(int(cookies["DedeUserID"]))
                            except ValueError:
                                pass
                        save_cookies(cookies)
                        self.app.ui_call(lambda: [
                            self._on_login_success(cookies),
                            dlg.destroy()
                        ])
                        return
                    elif code == 86038:
                        self.app.ui_call(lambda: status.set("二维码已过期"))
                        return
                    elif code == 86090:
                        self.app.ui_call(lambda: status.set("已扫码，请在手机上确认..."))
                    time.sleep(2)

                self.app.ui_call(lambda: status.set("登录超时"))
            except Exception as e:
                self.app.ui_call(lambda: status.set(f"错误: {e}"))

        threading.Thread(target=_poll, daemon=True).start()

        ttk.Button(dlg, text="取消", command=dlg.destroy).pack(pady=10)
        dlg.wait_window()

    def _on_login_success(self, cookies: dict):
        self.app.client = BiliClient(cookies)
        uid = cookies.get("DedeUserID", "?")
        self.status_var.set(f"已登录 UID: {uid}")
        self.log(f"登录成功: UID={uid}")

    def _load_cached_cookies(self):
        cookies = load_cookies()
        if cookies and "SESSDATA" in cookies:
            self._on_login_success(cookies)
            self.log("已加载缓存 Cookie")
        else:
            self.log("未找到有效缓存 Cookie")

    def _logout(self):
        self.app.client = None
        self.status_var.set("未登录")
        self.log("已注销")

    # ── 拉取关注 ──

    def _start_fetch(self):
        if not self.app.client:
            from tkinter import messagebox
            messagebox.showwarning("未登录", "请先扫码登录")
            return

        self._start_op()
        client = self.app.client

        def _run():
            try:
                def progress(pg, total, count):
                    if self._stop_requested:
                        raise RuntimeError("用户停止")
                    pct = (pg / total) * 100
                    self.app.ui_call(lambda: self.progress.configure(value=pct))
                    self.app.ui_call(lambda: self.progress_label.configure(
                        text=f"第 {pg}/{total} 页, 已拉取 {count} 条"))

                follows, total = fetch_all_followings(
                    client, progress_callback=progress
                )
                if self._stop_requested:
                    self.app.ui_call(lambda: self.log("拉取已停止"))
                    return

                database.save_follows(follows)
                self.app.ui_call(lambda: [
                    self.log(f"拉取完成: {len(follows)}/{total}"),
                    self._refresh_stats()
                ])
            except RuntimeError:
                self.app.ui_call(lambda: self.log("拉取已停止"))
            except Exception as e:
                self.app.ui_call(lambda: self.log(f"拉取失败: {e}"))
            finally:
                self.app.ui_call(lambda: [
                    self.progress.configure(value=0),
                    self.progress_label.configure(text=""),
                    self._end_op()
                ])

        threading.Thread(target=_run, daemon=True).start()

    def _start_special_fetch(self):
        if not self.app.client:
            from tkinter import messagebox
            messagebox.showwarning("未登录", "请先扫码登录")
            return

        client = self.app.client

        def _run():
            try:
                uids = []
                pn = 1
                while True:
                    r = client.get(
                        "https://api.bilibili.com/x/relation/tags",
                        params={"tagid": -10, "pn": pn, "ps": 50}
                    )
                    if r.get("code") != 0:
                        break
                    items = r.get("data", [])
                    if not items:
                        break
                    for u in items:
                        uids.append(u["mid"])
                    pn += 1

                conn = database.get_conn()
                for uid in uids:
                    conn.execute(
                        "INSERT OR REPLACE INTO verdicts (mid, verdict, rule_keep, keep_score) "
                        "VALUES (?, 'protected', '特别关注', 999)",
                        (uid,)
                    )
                conn.commit()
                conn.close()
                self.app.ui_call(lambda: self.log(f"特别关注: {len(uids)} 个已保护 ⭐"))
            except Exception as e:
                self.app.ui_call(lambda: self.log(f"拉取特别关注失败: {e}"))

        threading.Thread(target=_run, daemon=True).start()

    # ── 统计 ──

    def _refresh_stats(self):
        try:
            stats = database.get_stats()
            self.stats_var.set(
                f"总关注: {stats.get('total_follows', 0)}  |  "
                f"已探测: {stats.get('total_probes', 0)}  |  "
                f"保留: {stats.get('verdict_keep', 0)}  |  "
                f"待删: {stats.get('verdict_delete', 0)}  |  "
                f"未审: {stats.get('verdict_unreviewed', 0)}"
            )
        except Exception:
            self.stats_var.set("统计加载失败")
