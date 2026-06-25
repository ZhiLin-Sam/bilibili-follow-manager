"""标签页面 (占位)"""

import tkinter.ttk as ttk

from .. import pages as page_registry
from .base import BasePage


@page_registry.register_page
class TagsPage(BasePage):
    page_id = "tags"
    title = "标签"
    order = 11

    def _build_icon(self):
        from ..app import _icon_tags, _make_icon

        return _make_icon(_icon_tags)

    def _build(self, parent: ttk.Frame) -> None:
        super()._build(parent)
        f = parent
        ttk.Label(f, text="批量备注/标签", style="Header.TLabel").pack(anchor="w", pady=(0, 5))
        ttk.Label(f, text="自定义标签分组管理 (开发中...)", style="Subtitle.TLabel").pack(
            anchor="w"
        )
