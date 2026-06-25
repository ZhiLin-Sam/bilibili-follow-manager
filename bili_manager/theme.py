"""VS Code Dark+ 暗色主题 — ttk 样式配置"""

import tkinter as tk
import tkinter.ttk as ttk

# ── 调色板 ──────────────────────────────
BG0 = "#1e1e1e"       # 主背景
BG1 = "#252526"       # 侧边栏/面板背景
BG2 = "#2d2d30"       # 输入框/列表背景
BG3 = "#3e3e42"       # 边框/分隔线
FG0 = "#d4d4d4"       # 主文字
FG1 = "#808080"       # 次要文字
ACCENT = "#569cd6"    # 强调色 (蓝)
ACCENT_HI = "#4fc1ff"  # 悬停高亮
GREEN = "#6a9955"     # 成功/保留
RED = "#f44747"        # 危险/删除
YELLOW = "#dcdcaa"     # 警告/待审
ORANGE = "#ce9178"     # 次要警告

FONT = ("Segoe UI", 9)
FONT_BOLD = ("Segoe UI", 9, "bold")
FONT_MONO = ("Cascadia Code", 9)


def apply_theme(root: tk.Tk) -> ttk.Style:
    """应用 VS Code Dark+ 主题到 tk 和 ttk 控件"""
    style = ttk.Style(root)

    # ── 基础 ──
    root.configure(bg=BG0)
    style.theme_use("clam")

    style.configure(".", background=BG0, foreground=FG0, font=FONT,
                    borderwidth=0, troughcolor=BG1)

    # ── 框架 ──
    style.configure("TFrame", background=BG0)
    style.configure("Sidebar.TFrame", background=BG1)
    style.configure("SidebarBtn.TFrame", background=BG1)
    style.configure("Content.TFrame", background=BG0)

    # ── 标签 ──
    style.configure("TLabel", background=BG0, foreground=FG0, font=FONT)
    style.configure("Sidebar.TLabel", background=BG1, foreground=FG0, font=FONT)
    style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"), foreground=FG0, background=BG0)
    style.configure("Subtitle.TLabel", font=("Segoe UI", 10), foreground=FG1, background=BG0)
    style.configure("Mono.TLabel", font=FONT_MONO, foreground=FG0, background=BG0)
    style.configure("Success.TLabel", foreground=GREEN, font=FONT_BOLD)
    style.configure("Danger.TLabel", foreground=RED, font=FONT_BOLD)
    style.configure("Warn.TLabel", foreground=YELLOW, font=FONT_BOLD)

    # ── 按钮 ──
    style.configure("TButton", background=BG2, foreground=FG0, font=FONT,
                    borderwidth=1, relief="flat", padding=(12, 4))
    style.map("TButton",
              background=[("active", BG3), ("pressed", ACCENT), ("disabled", BG1)],
              foreground=[("disabled", FG1)])
    style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff",
                    font=FONT_BOLD, padding=(14, 5))
    style.map("Accent.TButton",
              background=[("active", ACCENT_HI), ("disabled", BG2)],
              foreground=[("disabled", FG1)])
    style.configure("Danger.TButton", background="#5a1a1a", foreground=RED,
                    font=FONT_BOLD, padding=(14, 5))
    style.map("Danger.TButton",
              background=[("active", "#8a2a2a"), ("disabled", BG2)],
              foreground=[("disabled", FG1)])
    style.configure("Sidebar.TButton", background=BG1, foreground=FG0, font=FONT,
                    borderwidth=0, relief="flat", padding=(8, 6), anchor="w")
    style.map("Sidebar.TButton",
              background=[("active", BG2), ("pressed", ACCENT)])

    # ── 侧边栏激活按钮 ──
    style.configure("SidebarActive.TButton", background=ACCENT, foreground="#ffffff",
                    font=FONT_BOLD, borderwidth=0, relief="flat", padding=(8, 6), anchor="w")

    # ── 折叠按钮 ──
    style.configure("Collapse.TButton", background=BG1, foreground=FG1,
                    font=("Segoe UI", 8), borderwidth=0, relief="flat", padding=(4, 2))

    # ── 输入框 ──
    style.configure("TEntry", fieldbackground=BG2, foreground=FG0, font=FONT,
                    borderwidth=1, insertcolor=FG0)
    style.map("TEntry", fieldbackground=[("disabled", BG1)])

    # ── 进度条 ──
    style.configure("TProgressbar", background=ACCENT, troughcolor=BG2,
                    borderwidth=0, thickness=6)

    # ── 标签页 ──
    style.configure("TNotebook", background=BG0, borderwidth=0)
    style.configure("TNotebook.Tab", background=BG1, foreground=FG0, font=FONT,
                    borderwidth=0, padding=(16, 6))
    style.map("TNotebook.Tab",
              background=[("selected", BG0), ("active", BG2)],
              foreground=[("selected", ACCENT)])

    # ── Treeview ──
    style.configure("Treeview", background=BG2, foreground=FG0, font=FONT,
                    fieldbackground=BG2, borderwidth=0, rowheight=26)
    style.configure("Treeview.Heading", background=BG1, foreground=FG0,
                    font=FONT_BOLD, borderwidth=0, relief="flat", padding=(6, 4))
    style.map("Treeview",
              background=[("selected", ACCENT)],
              foreground=[("selected", "#ffffff")])
    style.map("Treeview.Heading",
              background=[("active", BG2)])

    # ── 滚动条 ──
    style.configure("TScrollbar", background=BG2, troughcolor=BG1,
                    borderwidth=0, arrowsize=14, arrowcolor=FG1)
    style.map("TScrollbar",
              background=[("active", BG3)])

    # ── 分隔线 ──
    style.configure("TSeparator", background=BG3)

    # ── 标签框架 ──
    style.configure("TLabelframe", background=BG0, foreground=FG0, borderwidth=1)
    style.configure("TLabelframe.Label", background=BG0, foreground=FG1, font=FONT_BOLD)

    # ── tk 原生控件配色 ──
    root.option_add("*Text.Background", BG2)
    root.option_add("*Text.Foreground", FG0)
    root.option_add("*Text.Font", FONT_MONO)
    root.option_add("*Text.InsertBackground", FG0)
    root.option_add("*Text.SelectBackground", ACCENT)
    root.option_add("*Text.SelectForeground", "#ffffff")
    root.option_add("*Listbox.Background", BG2)
    root.option_add("*Listbox.Foreground", FG0)
    root.option_add("*Listbox.Font", FONT)
    root.option_add("*Listbox.SelectBackground", ACCENT)
    root.option_add("*Listbox.SelectForeground", "#ffffff")

    return style
