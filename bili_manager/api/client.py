"""HTTP 客户端 — 统一的 cookie/session 管理"""

import time
from typing import Any

import requests

from ..utils.helpers import logger

BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
}


class BiliClient:
    """统一 B 站 API 请求客户端"""

    def __init__(self, cookies: dict | None = None):
        self.session = requests.Session()
        self.session.headers.update(BASE_HEADERS)
        if cookies:
            self.set_cookies(cookies)

    def set_cookies(self, cookies: dict) -> None:
        for name, value in cookies.items():
            self.session.cookies.set(name, value, domain=".bilibili.com")

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        resp = self.session.request(method, url, **kwargs)
        return resp

    def get(self, url: str, **kwargs) -> dict[str, Any]:
        resp = self._request("GET", url, **kwargs)
        try:
            return resp.json()
        except Exception:
            return {"code": -1, "message": resp.text[:200]}

    def post(self, url: str, **kwargs) -> dict[str, Any]:
        resp = self._request("POST", url, **kwargs)
        try:
            return resp.json()
        except Exception:
            return {"code": -1, "message": resp.text[:200]}

    def get_json_with_retry(self, url: str, max_retries: int = 3, **kwargs) -> dict[str, Any]:
        """带重试的 GET 请求"""
        for attempt in range(max_retries):
            try:
                resp = self._request("GET", url, **kwargs)
                if resp.status_code == 412:
                    logger.warning("412 触发风控, 等待 5s 重试...")
                    time.sleep(5)
                    continue
                return resp.json()
            except Exception as e:
                logger.warning(f"请求失败 (attempt {attempt+1}/{max_retries}): {e}")
                time.sleep(1)
        return {"code": -1, "message": "max retries exceeded"}

    @property
    def uid(self) -> str:
        return self.session.cookies.get("DedeUserID", "") or ""

    @property
    def csrf(self) -> str:
        return self.session.cookies.get("bili_jct", "") or ""
