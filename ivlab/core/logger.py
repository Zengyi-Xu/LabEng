"""日志配置"""
import logging
import sys
from pathlib import Path


def setup_logger(name: str = "ivlab", level=logging.DEBUG, log_dir: str = "./logs") -> logging.Logger:
    """设置日志记录器"""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    # 控制台输出
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # 文件输出
    Path(log_dir).mkdir(exist_ok=True)
    fh = logging.FileHandler(Path(log_dir) / "ivlab.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fmt2 = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    fh.setFormatter(fmt2)
    logger.addHandler(fh)

    return logger
