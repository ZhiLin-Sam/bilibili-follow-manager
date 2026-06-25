"""导出页面 (占位)"""

import tkinter as tk
import tkinter.ttk as ttk

from .base import BasePage
from .. import pages as page_registry


@page_registry.register_page
class ExportPage(BasePage):
    page_id = "export"
    title = "导出"
    order = 10

    def _build_icon(self):
        from ..app import _icon_export, _make_icon
        return _make_icon(_icon_export)

    def _build(self, parent: ttk.Frame) -> None:
        super()._build(parent)
        f = parent
        ttk.Label(f, text="数据导出", style="Header.TLabel").pack(anchor="w", pady=(0, 5))
        ttk.Label(f, text="导出 CSV / JSON / HTML 报告 (开发中...)",
                  style="Subtitle.TLabel").pack(anchor="w")
