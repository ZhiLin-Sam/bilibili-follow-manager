"""pywebview 桌面壳 — 嵌入 React 前端 + 启动 FastAPI 后端"""

from __future__ import annotations

import threading
import time

import uvicorn


def start_api():
    """Start FastAPI server on :9000 in a daemon thread."""
    from bili_manager.api_http import app
    uvicorn.run(app, host="127.0.0.1", port=9000, log_level="info")


def start_webview():
    """Launch pywebview window pointing to Vite dev server or built dist."""
    import webview

    # Try Vite dev server first, fall back to dist
    url = "http://localhost:5173"

    webview.create_window(
        "BiliManager",
        url,
        width=1200,
        height=750,
        min_size=(900, 500),
    )
    webview.start(debug=False)


def main():
    # Start API server in background
    api_thread = threading.Thread(target=start_api, daemon=True)
    api_thread.start()

    # Wait for API to be ready
    import requests
    for _ in range(20):
        try:
            requests.get("http://127.0.0.1:9000/api/status", timeout=1)
            break
        except Exception:
            time.sleep(0.5)

    # Start pywebview
    start_webview()


if __name__ == "__main__":
    main()
