"""页面基类 — 所有功能页面继承此抽象类"""

from __future__ import annotations

import tkinter.ttk as ttk
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class BasePage(ABC):
    """功能页面抽象基类

    子类必须定义:
      - page_id: 唯一标识符 (如 'fetch', 'review')
      - title: 页面标题
      - order: 侧边栏排序 (0=最前)
      - _build_icon(): 返回 18x18 的 Pillow Image
    """

    page_id: str
    title: str
    order: int = 100

    def __init__(self, app):
        self.app = app
        self.frame: ttk.Frame | None = None
        self._icon_ref = None  # 保持 PhotoImage 引用
        # 注册侧边栏导航按钮
        icon = self._build_icon()
        self.app.register_sidebar_btn(self.page_id, self.title, icon)

    @abstractmethod
    def _build_icon(self):
        """返回 PIL.Image (18x18 RGBA)"""

    def _build(self, parent: ttk.Frame) -> None:
        """构建页面 UI — 子类重写此方法"""
        self.frame = parent

    def on_enter(self) -> None:
        """页面被切换到时的回调"""

    def on_leave(self) -> None:
        """页面被切走时的回调"""

    def log(self, msg: str) -> None:
        """写入应用日志"""
        self.app.log(msg)

    @property
    def client(self):
        return self.app.client

    @property
    def engine(self):
        return self.app.engine
