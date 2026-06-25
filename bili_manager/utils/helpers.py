"""工具函数"""

import logging
import sys
from pathlib import Path

logger = logging.getLogger("bili_manager")


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                          datefmt="%H:%M:%S")
    )
    logger.addHandler(handler)
    logger.setLevel(level)


def get_data_dir() -> Path:
    return Path(__file__).parent.parent.parent / "data"


def get_config_dir() -> Path:
    return Path(__file__).parent.parent.parent / "config"
