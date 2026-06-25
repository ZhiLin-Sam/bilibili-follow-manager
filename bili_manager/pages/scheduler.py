"""定时刷新页面 (占位)"""

import tkinter as tk
import tkinter.ttk as ttk

from .base import BasePage
from .. import pages as page_registry


@page_registry.register_page
class SchedulerPage(BasePage):
    page_id = "scheduler"
    title = "定时"
    order = 13

    def _build_icon(self):
        from ..app import _icon_clock, _make_icon
        return _make_icon(_icon_clock)

    def _build(self, parent: ttk.Frame) -> None:
        super()._build(parent)
        f = parent
        ttk.Label(f, text="定时刷新", style="Header.TLabel").pack(anchor="w", pady=(0, 5))
        ttk.Label(f, text="自动定时拉取关注 + 对比变化 (开发中...)",
                  style="Subtitle.TLabel").pack(anchor="w")
