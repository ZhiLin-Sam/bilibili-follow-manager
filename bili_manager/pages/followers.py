"""粉丝分析页面 (占位)"""

import tkinter.ttk as ttk

from .. import pages as page_registry
from .base import BasePage


@page_registry.register_page
class FollowersPage(BasePage):
    page_id = "followers"
    title = "粉丝"
    order = 12

    def _build_icon(self):
        from ..app import _icon_followers, _make_icon
        return _make_icon(_icon_followers)

    def _build(self, parent: ttk.Frame) -> None:
        super()._build(parent)
        f = parent
        ttk.Label(f, text="粉丝分析", style="Header.TLabel").pack(anchor="w", pady=(0, 5))
        ttk.Label(f, text="僵尸粉检测 / 互关分析 (开发中...)",
                  style="Subtitle.TLabel").pack(anchor="w")
