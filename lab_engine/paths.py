"""应用路径统一入口。

开发时：项目根目录（本文件的上一级）。
PyInstaller 打包后：exe 所在目录（数据、例程、参数都在 exe 旁边，便于用户查看与扩展）。
"""
import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    return app_root() / "data"


def routines_dir() -> Path:
    """例程目录。打包后放在 exe 旁边的 routines/，方便直接增删例程文件。"""
    if getattr(sys, "frozen", False):
        return app_root() / "routines"
    return app_root() / "lab_engine" / "routines"


def systems_dir() -> Path:
    """组合测试系统（.labsetup.json）默认存放目录。"""
    return data_dir() / "systems"


def draft_path() -> Path:
    return data_dir() / "draft_setup.json"


def param_store_path() -> Path:
    return data_dir() / "routine_params.json"
