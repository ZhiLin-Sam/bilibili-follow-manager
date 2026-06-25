"""取关 API"""

import time

from ..utils.helpers import logger
from .client import BiliClient

UNFOLLOW_URL = "https://api.bilibili.com/x/relation/modify"


def unfollow_single(client: BiliClient, fid: str) -> bool:
    """
    取消关注单个用户.

    Returns:
        True 成功, False 失败
    """
    data = {
        "fid": fid,
        "act": 2,  # 2=取消关注
        "re_src": 11,
        "csrf": client.csrf,
    }
    resp = client.post(UNFOLLOW_URL, data=data)
    if resp.get("code") == 0:
        return True
    else:
        logger.warning(f"取关 {fid} 失败: {resp}")
        return False


def batch_unfollow(
    client: BiliClient, uids: list[str], interval: float = 3.0, progress_callback=None
) -> tuple[int, int]:
    """
    批量取消关注.

    Args:
        client: BiliClient
        uids: 要取关的 UID 列表
        interval: 操作间隔(秒)
        progress_callback: fn(done, total, success_count)

    Returns:
        (成功数, 失败数)
    """
    success, fail = 0, 0
    total = len(uids)

    for i, uid in enumerate(uids):
        if i > 0:
            time.sleep(interval)

        if unfollow_single(client, uid):
            success += 1
        else:
            fail += 1

        if progress_callback:
            progress_callback(i + 1, total, success)

    logger.info(f"取关完成: {success}/{total} 成功, {fail} 失败")
    return success, fail
