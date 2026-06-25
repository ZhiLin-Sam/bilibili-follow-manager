"""Bilibili Follow Manager — 启动入口"""

from .app import BiliApp
from .utils.helpers import setup_logging


def main() -> None:
    setup_logging()
    app = BiliApp()
    app.mainloop()


if __name__ == "__main__":
    main()
