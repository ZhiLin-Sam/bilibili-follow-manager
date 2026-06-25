"""页面注册中心 — 自动发现 pages/ 目录下的页面模块"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BasePage

_registry: dict[str, type["BasePage"]] = {}


def register_page(page_cls: type["BasePage"]) -> type["BasePage"]:
    """装饰器: 将页面类注册到全局注册表"""
    _registry[page_cls.page_id] = page_cls
    return page_cls


def discover_pages() -> None:
    """自动发现 pages/ 目录下所有 .py 模块并导入 (触发 @register_page)"""
    pkg_dir = Path(__file__).parent
    for _, name, _ in pkgutil.iter_modules([str(pkg_dir)]):
        if name in ("base", "__init__"):
            continue
        importlib.import_module(f".{name}", package=__package__)


def get_pages() -> list[type["BasePage"]]:
    """按 order 排序的已注册页面列表"""
    return sorted(_registry.values(), key=lambda p: p.order)


def get_page(page_id: str) -> type["BasePage"] | None:
    return _registry.get(page_id)
