"""入口点"""

import sys

from .gui.main_window import BiliGUI
from .utils.helpers import setup_logging


def main():
    setup_logging()
    app = BiliGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
