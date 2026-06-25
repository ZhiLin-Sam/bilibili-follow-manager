"""Bilibili QR 扫码登录"""

import json
import time
from pathlib import Path

import qrcode
import requests

from ..utils.helpers import get_data_dir, logger

QR_GENERATE_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
QR_POLL_URL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"
COOKIE_FILE_NAME = "cookies.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com/",
}


def _cookie_path() -> Path:
    """Returns path to cookie file."""
    return get_data_dir() / COOKIE_FILE_NAME


def load_cookies() -> dict | None:
    """Load saved cookies from disk."""
    cp = _cookie_path()
    if cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def save_cookies(cookies: dict) -> None:
    """Persist cookies to disk."""
    get_data_dir().mkdir(parents=True, exist_ok=True)
    _cookie_path().write_text(json.dumps(cookies, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    logger.info("Cookies saved")


def has_valid_cookies() -> bool:
    """Quick check if cookies exist (does not validate expiry)."""
    cookies = load_cookies()
    return cookies is not None and "SESSDATA" in cookies


def print_qr_ascii(url: str) -> None:
    """Print QR code as ASCII art in terminal."""
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)


def get_qr_image(url: str) -> bytes:
    """Generate QR code PNG bytes for GUI display."""
    import io
    qr = qrcode.QRCode(border=2, box_size=8)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def login_qrcode(as_image: bool = False, poll_timeout: float = 180.0):
    """
    扫码登录流程:
    1. 生成二维码 (可输出终端ASCII 或 返回PNG图片)
    2. 轮询扫码状态
    3. 返回 cookies

    Returns:
        tuple: (cookies_dict, qr_png_bytes_or_None)
    """
    session = requests.Session()
    session.headers.update(HEADERS)

    # Step 1: 生成二维码
    resp = session.get(QR_GENERATE_URL).json()
    if resp.get("code") != 0:
        raise RuntimeError(f"生成二维码失败: {resp}")

    qrcode_key = resp["data"]["qrcode_key"]
    qr_url = resp["data"]["url"]

    if as_image:
        qr_data = get_qr_image(qr_url)
    else:
        print_qr_ascii(qr_url)
        qr_data = None

    logger.info(f"二维码已生成, 有效期 {poll_timeout}s, 请使用哔哩哔哩APP扫码")

    # Step 2: 轮询
    start = time.time()
    while time.time() - start < poll_timeout:
        poll_resp = session.get(
            QR_POLL_URL,
            params={"qrcode_key": qrcode_key}
        ).json()

        code = poll_resp.get("data", {}).get("code", -1)
        message = poll_resp.get("data", {}).get("message", "")

        if code == 0:
            logger.info("扫码成功!")
            break
        elif code == 86038:
            raise RuntimeError("二维码已过期, 请重新获取")
        elif code == 86090:
            if not as_image:
                print("\r状态: 已扫码, 请在手机上确认...", end="")
        elif code == 86101:
            pass  # 等待扫码
        else:
            if not as_image:
                print(f"\r状态: {message}", end="")

        time.sleep(1.5)

    # Step 3: 提取 cookies
    cookies = {}
    for cookie in session.cookies:
        cookies[cookie.name] = cookie.value

    required = ["SESSDATA", "bili_jct", "DedeUserID"]
    missing = [k for k in required if k not in cookies]
    if missing:
        raise RuntimeError(f"登录未完成, 缺少必要 cookie: {missing}")

    # 补充 dedeuserid 格式
    from contextlib import suppress
    with suppress(ValueError):
        cookies["DedeUserID"] = str(int(cookies["DedeUserID"]))

    save_cookies(cookies)
    return cookies, qr_data
