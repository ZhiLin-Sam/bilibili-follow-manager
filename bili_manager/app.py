"""主应用 — 侧边栏导航 + 页面路由 + 暗色主题"""

from __future__ import annotations

import tkinter as tk
import tkinter.ttk as ttk
from typing import TYPE_CHECKING

# Pillow 几何图标工具
from PIL import Image, ImageDraw, ImageTk

from .db import database
from .rules.engine import RuleEngine
from .theme import ACCENT, BG0, BG1, FG0, FG1, RED, apply_theme
from .utils.helpers import logger

if TYPE_CHECKING:
    from .pages.base import BasePage


# ── 几何图标生成 ─────────────────────────
# 18x18 RGBA, 线宽 2, 颜色 #d4d4d4


def _make_icon(draw_fn) -> Image.Image:
    img = Image.new("RGBA", (18, 18), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw_fn(draw)
    return img


def _icon_home(draw):
    """小房子: 三角形屋顶 + 矩形屋身"""
    draw.polygon([(9, 1), (1, 7), (17, 7)], outline=FG0, width=1)
    draw.rectangle([3, 8, 15, 16], outline=FG0, width=1)
    draw.rectangle([5, 11, 7, 16], outline=FG0, width=1)
    draw.rectangle([10, 11, 12, 16], outline=FG0, width=1)


def _icon_fetch(draw):
    """下载箭头: 向下箭头 + 底部横线"""
    draw.line([(9, 1), (9, 11)], fill=FG0, width=2)
    draw.line([(4, 6), (9, 14), (14, 6)], fill=FG0, width=2)
    draw.line([(1, 16), (17, 16)], fill=FG0, width=2)


def _icon_filter(draw):
    """漏斗: 上宽下窄"""
    draw.polygon([(1, 1), (17, 1), (11, 8), (11, 16), (7, 14), (7, 8)], outline=FG0, width=1)


def _icon_review(draw):
    """清单: 列表项"""
    draw.rectangle([1, 1, 17, 4], outline=FG0, width=1)
    draw.rectangle([1, 7, 17, 10], outline=FG0, width=1)
    draw.rectangle([1, 13, 17, 16], outline=FG0, width=1)


def _icon_unfollow(draw):
    """X标记: 交叉线"""
    draw.line([(2, 2), (16, 16)], fill=RED, width=2)
    draw.line([(16, 2), (2, 16)], fill=RED, width=2)


def _icon_export(draw):
    """导出: 盒子 + 上箭头"""
    draw.rectangle([3, 7, 15, 16], outline=FG0, width=1)
    draw.polygon([(9, 1), (3, 8), (15, 8)], outline=FG0, width=1)
    draw.line([(9, 4), (9, 7)], fill=FG0, width=2)


def _icon_tags(draw):
    """标签: 标签形状"""
    draw.polygon([(1, 1), (13, 1), (17, 5), (17, 17), (1, 17)], outline=FG0, width=1)
    draw.ellipse([3, 4, 7, 8], outline=FG0, width=1)


def _icon_followers(draw):
    """双人: 两个圆+身体"""
    draw.ellipse([3, 1, 7, 6], outline=FG0, width=1)
    draw.ellipse([11, 1, 15, 6], outline=FG0, width=1)
    draw.line([(3, 7), (3, 14)], fill=FG0, width=1)
    draw.line([(7, 7), (7, 14)], fill=FG0, width=1)
    draw.line([(11, 7), (11, 14)], fill=FG0, width=1)
    draw.line([(15, 7), (15, 14)], fill=FG0, width=1)
    draw.line([(1, 16), (9, 10)], fill=FG0, width=1)
    draw.line([(9, 10), (17, 16)], fill=FG0, width=1)


def _icon_clock(draw):
    """时钟: 圆形 + 指针"""
    draw.ellipse([1, 1, 17, 17], outline=FG0, width=1)
    draw.line([(9, 9), (9, 4)], fill=FG0, width=1)
    draw.line([(9, 9), (13, 9)], fill=FG0, width=1)


def _icon_collapse(draw):
    """折叠: 双左箭头"""
    draw.line([(12, 2), (6, 9), (12, 16)], fill=FG1, width=2)
    draw.line([(16, 2), (10, 9), (16, 16)], fill=FG1, width=2)


def _icon_expand(draw):
    """展开: 双右箭头"""
    draw.line([(6, 2), (12, 9), (6, 16)], fill=FG1, width=2)
    draw.line([(2, 2), (8, 9), (2, 16)], fill=FG1, width=2)


# ── 图标工厂 ──
ICON_FNS = {
    "home": _icon_home,
    "fetch": _icon_fetch,
    "filter": _icon_filter,
    "review": _icon_review,
    "unfollow": _icon_unfollow,
    "export": _icon_export,
    "tags": _icon_tags,
    "followers": _icon_followers,
    "scheduler": _icon_clock,
}


# 默认图标 (占位方框)
def _icon_default(draw):
    draw.rectangle([2, 2, 16, 16], outline=FG0, width=1)


class BiliApp(tk.Tk):
    """主应用程序"""

    def __init__(self):
        super().__init__()
        self.title("Bilibili Follow Manager")
        self.geometry("1200x750")
        self.minsize(900, 500)
        self.configure(bg=BG0)

        # ── 全局状态 ──
        self.client = None
        self.engine: RuleEngine = RuleEngine()
        self.current_page_id: str | None = None

        # ── 主题 ──
        apply_theme(self)

        # ── 主布局: 侧边栏 + 内容区 ──
        self.sidebar = ttk.Frame(self, style="Sidebar.TFrame", width=180)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        sep = ttk.Separator(self, orient=tk.VERTICAL)
        sep.pack(side=tk.LEFT, fill=tk.Y)

        self.content = ttk.Frame(self, style="Content.TFrame")
        self.content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ── 状态栏 ──
        self.status = ttk.Frame(self, style="Sidebar.TFrame", height=28)
        self.status.pack(side=tk.BOTTOM, fill=tk.X)
        self.status.pack_propagate(False)
        self.status_label = ttk.Label(self.status, text="就绪", style="Sidebar.TLabel")
        self.status_label.pack(side=tk.LEFT, padx=10)

        # ── 侧边栏内容 ──
        self._build_sidebar()

        # ── 页面容器 ──
        self.pages: dict[str, BasePage] = {}
        self.page_frame = ttk.Frame(self.content, style="Content.TFrame")
        self.page_frame.pack(fill=tk.BOTH, expand=True)

        # ── 自动发现并初始化页面 ──
        from .pages import discover_pages, get_pages

        discover_pages()
        for page_cls in get_pages():
            page = page_cls(self)
            self.pages[page.page_id] = page

        # ── 默认首页 ──
        first = get_pages()[0].page_id if get_pages() else None
        if first:
            self.switch_page(first)

        # ── 数据库初始化 ──
        database.init_db()

    # ── 侧边栏 ──────────────────────────

    def _build_sidebar(self) -> None:
        """构建侧边栏 UI"""
        # 标题
        hdr = ttk.Frame(self.sidebar, style="Sidebar.TFrame")
        hdr.pack(fill=tk.X, pady=(15, 10), padx=12)
        ttk.Label(
            hdr,
            text="BiliManager",
            font=("Segoe UI", 11, "bold"),
            foreground=ACCENT,
            background=BG1,
        ).pack(anchor="w")

        # 导航按钮容器
        self._sidebar_btns: dict[str, ttk.Button] = {}
        self._sidebar_icons: list[ImageTk.PhotoImage] = []  # 保持引用

        # 折叠/展开按钮
        self._collapsed = False
        self.sidebar_width = 180
        self._collapse_icon = ImageTk.PhotoImage(_make_icon(_icon_collapse))
        self._expand_icon = ImageTk.PhotoImage(_make_icon(_icon_expand))
        self._sidebar_icons.extend([self._collapse_icon, self._expand_icon])

        self._toggle_btn = ttk.Button(
            self.sidebar,
            image=self._collapse_icon,
            style="Collapse.TButton",
            command=self._toggle_sidebar,
        )
        self._toggle_btn.pack(side=tk.BOTTOM, anchor="w", padx=6, pady=6)

    def register_sidebar_btn(self, page_id: str, text: str, icon: Image.Image) -> None:
        """注册侧边栏导航按钮"""
        photo = ImageTk.PhotoImage(icon)
        self._sidebar_icons.append(photo)

        btn = ttk.Button(
            self.sidebar,
            text=f"  {text}",
            image=photo,
            compound=tk.LEFT,
            style="Sidebar.TButton",
            command=lambda pid=page_id: self._switch_page_cmd(pid),
        )
        btn.pack(fill=tk.X, padx=6, pady=1)
        self._sidebar_btns[page_id] = btn

    def _toggle_sidebar(self) -> None:
        """折叠/展开侧边栏"""
        if self._collapsed:
            self.sidebar.configure(width=180)
            self._toggle_btn.configure(image=self._collapse_icon)
            for btn in self._sidebar_btns.values():
                btn.configure(text=f"  {btn.cget('text').strip()}")
        else:
            self.sidebar.configure(width=48)
            self._toggle_btn.configure(image=self._expand_icon)
            for btn in self._sidebar_btns.values():
                btn.configure(text="")
        self._collapsed = not self._collapsed

    # ── 页面切换 ────────────────────────

    def _switch_page_cmd(self, page_id: str) -> None:
        """侧边栏按钮回调包装 (避免 lambda 类型推断问题)"""
        self.switch_page(page_id)

    def switch_page(self, page_id: str) -> None:
        """切换到指定页面"""
        if page_id not in self.pages:
            return

        # 离开旧页面
        if self.current_page_id and self.current_page_id in self.pages:
            self.pages[self.current_page_id].on_leave()

        # 隐藏所有页面
        for p in self.pages.values():
            if p.frame:
                p.frame.pack_forget()

        # 显示新页面
        page = self.pages[page_id]
        if page.frame is None:
            # 首次构建
            page.frame = ttk.Frame(self.page_frame, style="Content.TFrame")
            page._build(page.frame)
        page.frame.pack(fill=tk.BOTH, expand=True)
        page.on_enter()

        self.current_page_id = page_id

        # 更新侧边栏按钮样式
        for pid, btn in self._sidebar_btns.items():
            btn.configure(style="SidebarActive.TButton" if pid == page_id else "Sidebar.TButton")

    def log(self, msg: str) -> None:
        """更新状态栏消息 + 终端日志"""
        logger.info(msg)
        self.status_label.configure(text=msg)

    # ── 线程安全 UI 更新 ────────────────

    def ui_call(self, fn, *args) -> None:
        """在主线程执行 UI 操作"""
        self.after(0, fn, *args)
