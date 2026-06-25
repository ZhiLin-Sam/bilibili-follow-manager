"""账号信息 API"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .client import BiliClient
from ..utils.helpers import logger

CARD_URL = "https://api.bilibili.com/x/web-interface/card"
RELATION_STAT_URL = "https://api.bilibili.com/x/relation/stat"
UPSTAT_URL = "https://api.bilibili.com/x/space/upstat"
NAVNUM_URL = "https://api.bilibili.com/x/space/navnum"


def _safe_int(val, default: int = -1) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def probe_single(client: BiliClient, uid: str) -> dict:
    """探测单个账号的活跃度数据."""
    result = {
        "uid": uid,
        "archive_count": -1,
        "video_count": -1,
        "follower": -1,
        "following": -1,
        "like_num": -1,
        "total_view": -1,
        "total_likes": -1,
        "level": -1,
        "spacesta": -999,
    }

    try:
        data = client.get_json_with_retry(CARD_URL, params={"mid": uid})
        if data.get("code") == 0:
            card = data["data"].get("card", {})
            result["archive_count"] = _safe_int(card.get("archive_count"), -1)
            result["follower"] = _safe_int(card.get("follower"), -1)
            result["like_num"] = _safe_int(card.get("like_num"), -1)
            result["level"] = _safe_int(card.get("level_info", {}).get("current_level"), -1)
            if card.get("spacesta") is not None:
                result["spacesta"] = int(card["spacesta"])
    except Exception as e:
        logger.debug(f"card API failed for {uid}: {e}")

    try:
        data = client.get_json_with_retry(RELATION_STAT_URL, params={"vmid": uid})
        if data.get("code") == 0:
            result["following"] = _safe_int(data["data"].get("following"), -1)
            if result["follower"] == -1:
                result["follower"] = _safe_int(data["data"].get("follower"), -1)
    except Exception as e:
        logger.debug(f"relation/stat API failed for {uid}: {e}")

    try:
        data = client.get_json_with_retry(UPSTAT_URL, params={"mid": uid})
        if data.get("code") == 0:
            result["total_view"] = _safe_int(data["data"].get("archive", {}).get("view"), -1)
            result["total_likes"] = _safe_int(data["data"].get("likes"), -1)
    except Exception as e:
        logger.debug(f"upstat API failed for {uid}: {e}")

    try:
        data = client.get_json_with_retry(NAVNUM_URL, params={"mid": uid})
        if data.get("code") == 0:
            result["video_count"] = _safe_int(data["data"].get("video"), -1)
    except Exception as e:
        logger.debug(f"navnum API failed for {uid}: {e}")

    # 计算关注/粉丝比
    if result["follower"] > 0 and result["following"] > 0:
        result["ff_ratio"] = round(result["following"] / result["follower"], 2)
    elif result["follower"] == 0 and result["following"] > 50:
        result["ff_ratio"] = 999.0
    else:
        result["ff_ratio"] = 0.0

    return result


def batch_probe(
    client: BiliClient,
    uids: list[str],
    concurrency: int = 5,
    batch_delay: float = 2.0,
    progress_callback=None
) -> list[dict]:
    """
    批量探测账号数据.

    Args:
        client: BiliClient
        uids: UID 列表
        concurrency: 并发数
        batch_delay: 每批间隔(秒)
        progress_callback: 进度回调 fn(done, total)

    Returns:
        探测结果列表
    """
    results = []
    total = len(uids)

    for i in range(0, total, concurrency):
        batch = uids[i:i + concurrency]
        with ThreadPoolExecutor(max_workers=len(batch)) as executor:
            futures = {executor.submit(probe_single, client, uid): uid for uid in batch}
            for future in as_completed(futures):
                results.append(future.result())

        done = min(i + concurrency, total)
        if progress_callback:
            progress_callback(done, total)

        if done < total:
            time.sleep(batch_delay)

    return results
