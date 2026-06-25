"""关注列表 API"""

import time
from typing import Generator

from .client import BiliClient
from ..utils.helpers import logger

FOLLOWING_URL = "https://api.bilibili.com/x/relation/followings"


def fetch_all_followings(
    client: BiliClient,
    vmid: str | None = None,
    page_size: int = 50,
    delay: float = 0.3,
    progress_callback=None
) -> tuple[list[dict], int]:
    """
    拉取全部关注列表.

    Args:
        client: 已认证的 BiliClient
        vmid: 目标 UID (默认当前用户)
        page_size: 每页数量
        delay: 页间延迟
        progress_callback: 进度回调 fn(current_page, total_pages, fetched_count)

    Returns:
        (关注列表, 总关注数)
    """
    if vmid is None:
        vmid = client.uid

    all_followings = []
    page = 1

    # 先拉第一页获取总数
    params = {"vmid": vmid, "pn": page, "ps": page_size, "order": "desc"}
    data = client.get(FOLLOWING_URL, params=params)

    if data.get("code") != 0:
        logger.error(f"获取关注列表失败: {data}")
        return [], 0

    total = data["data"]["total"]
    total_pages = (total + page_size - 1) // page_size
    items = data["data"].get("list", [])
    all_followings.extend(items)

    if progress_callback:
        progress_callback(page, total_pages, len(all_followings))

    # 拉剩余页
    for page in range(2, total_pages + 1):
        time.sleep(delay)
        params["pn"] = page
        data = client.get(FOLLOWING_URL, params=params)
        if data.get("code") != 0:
            logger.warning(f"第 {page} 页拉取失败: {data}")
            continue

        items = data["data"].get("list", [])
        all_followings.extend(items)

        if progress_callback:
            progress_callback(page, total_pages, len(all_followings))

    logger.info(f"关注列表拉取完成: {len(all_followings)}/{total}")
    return all_followings, total
