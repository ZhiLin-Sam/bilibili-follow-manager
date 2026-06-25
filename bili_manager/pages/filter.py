"""过滤页面 — 规则过滤 + 深度探测"""

import threading
import tkinter as tk
import tkinter.ttk as ttk

from .base import BasePage
from .. import pages as page_registry
from ..db import database
from ..api.account import batch_probe
from ..theme import BG0


@page_registry.register_page
class FilterPage(BasePage):
    page_id = "filter"
    title = "过滤"
    order = 2

    def _build_icon(self):
        from ..app import _icon_filter, _make_icon
        return _make_icon(_icon_filter)

    def _build(self, parent: ttk.Frame) -> None:
        super()._build(parent)
        f = parent

        ttk.Label(f, text="规则过滤 & 深度探测", style="Header.TLabel").pack(anchor="w", pady=(0, 5))
        ttk.Label(f, text="应用预设规则 + 自定义规则自动判定，深度探测拉取空间数据",
                  style="Subtitle.TLabel").pack(anchor="w", pady=(0, 10))

        btn_row = ttk.Frame(f)
        btn_row.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(btn_row, text="运行规则过滤", style="Accent.TButton",
                   command=self._apply_rules).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="深度探测 (活跃度分析)",
                   command=self._start_probe).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="⏹ 停止", command=self._stop_op,
                   state=tk.DISABLED).pack(side=tk.LEFT, padx=(0, 8))

        self._btn_stop = btn_row.winfo_children()[-1]
        self._op_active = False
        self._stop_requested = False

        self.progress = ttk.Progressbar(f, mode="determinate")
        self.progress.pack(fill=tk.X, pady=(5, 5))
        self.progress_label = ttk.Label(f, text="", style="Subtitle.TLabel")
        self.progress_label.pack(anchor="w")

        self.result_var = tk.StringVar(value="")
        ttk.Label(f, textvariable=self.result_var, style="Mono.TLabel").pack(anchor="w", pady=(10, 0))

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

    def _apply_rules(self):
        from .review import ReviewPage
        conn = database.get_conn()
        rows = conn.execute("SELECT * FROM follows").fetchall()
        conn.close()

        if not rows:
            self.log("没有关注数据，请先拉取")
            return

        engine = self.engine
        verdicts = []
        keep_count = delete_count = protected_count = 0

        for r in rows:
            official_type = r["official_verify_type"]
            is_vip = r["vip_status"] == 1
            result = engine.evaluate_signature(dict(r), official_type, is_vip)

            if official_type > 0:
                verdict = "protected"
                protected_count += 1
            elif result.keep_score >= result.delete_score:
                verdict = "keep"
                keep_count += 1
            elif result.delete_score >= 40:
                verdict = "delete"
                delete_count += 1
            else:
                verdict = "unreviewed"

            verdicts.append({
                "mid": r["mid"],
                "verdict": verdict,
                "rule_keep": ",".join(result.matched_keep),
                "rule_delete": ",".join(result.matched_delete),
                "keep_score": result.keep_score,
                "delete_score": result.delete_score,
            })

        database.save_verdicts(verdicts)
        self.result_var.set(
            f"保留: {keep_count}  |  删除: {delete_count}  |  保护: {protected_count}  |  未审: {len(verdicts) - keep_count - delete_count - protected_count}"
        )
        self.log(f"规则已应用: {len(verdicts)} 条")

    def _start_probe(self):
        if not self.app.client:
            from tkinter import messagebox
            messagebox.showwarning("未登录", "请先登录")
            return

        conn = database.get_conn()
        rows = conn.execute("SELECT f.mid FROM follows f LEFT JOIN probes p ON f.mid = p.mid WHERE p.mid IS NULL OR p.spacesta = -999").fetchall()
        conn.close()

        if not rows:
            self.log("所有账号已探测")
            return

        uids = [str(r["mid"]) for r in rows]
        total = len(uids)
        self.log(f"开始深度探测 {total} 个账号...")

        self._start_op()
        client = self.app.client

        def _run():
            try:
                def progress(done, _total):
                    if self._stop_requested:
                        raise RuntimeError("用户停止")
                    pct = (done / total) * 100
                    self.app.ui_call(lambda: [
                        self.progress.configure(value=pct),
                        self.progress_label.configure(text=f"已探测: {done}/{total}")
                    ])

                results = batch_probe(client, uids, concurrency=5, batch_delay=3.0,
                                       progress_callback=progress)
                if self._stop_requested:
                    self.app.ui_call(lambda: self.log("探测已停止"))
                    return

                # 应用探测规则
                probe_verdicts = []
                for p in results:
                    probe_result = self.engine.evaluate_probe(p)
                    if probe_result.delete_score > 0:
                        probe_verdicts.append({
                            "mid": int(p["uid"]),
                            "verdict": "delete",
                            "rule_probe": ",".join(probe_result.matched_probe),
                            "delete_score": probe_result.delete_score + 100,
                        })
                    elif probe_result.keep_score > 0:
                        probe_verdicts.append({
                            "mid": int(p["uid"]),
                            "verdict": "keep",
                            "rule_probe": ",".join(probe_result.matched_keep),
                            "keep_score": probe_result.keep_score + 50,
                        })

                database.save_probes(results)
                if probe_verdicts:
                    database.save_verdicts(probe_verdicts)

                self.app.ui_call(lambda: [
                    self.log(f"探测完成: {len(results)} 个"),
                    self.result_var.set(f"探测完成: {len(results)} 个账号")
                ])
            except RuntimeError:
                self.app.ui_call(lambda: self.log("探测已停止"))
            except Exception as e:
                self.app.ui_call(lambda: self.log(f"探测失败: {e}"))
            finally:
                self.app.ui_call(lambda: [
                    self.progress.configure(value=0),
                    self.progress_label.configure(text=""),
                    self._end_op()
                ])

        threading.Thread(target=_run, daemon=True).start()
