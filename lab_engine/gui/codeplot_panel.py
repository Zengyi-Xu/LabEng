"""CodePlot 集成：在 LabEng 中弹出一个内嵌 CodePlot 的窗口。"""
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from lab_engine.gui.shell import COLOR_BG


_CODEPLOT_DIR = Path(__file__).resolve().parent.parent / "vendor" / "codeplot"


def open_codeplot_window(parent: tk.Misc) -> None:
    """打开 CodePlot v5（内嵌 Toplevel）。

    CodePlot 的 gallery/templates 都基于它自己的文件目录，
    因此把它所在目录临时加入 sys.path 后 import。
    """
    if str(_CODEPLOT_DIR) not in sys.path:
        sys.path.insert(0, str(_CODEPLOT_DIR))
    try:
        import codeplot as cp  # type: ignore
    except Exception as exc:  # pragma: no cover - 依赖缺失时给出友好提示
        from tkinter import messagebox
        messagebox.showerror("CodePlot 加载失败", str(exc))
        return

    win = tk.Toplevel(parent)
    win.title("CodePlot — 绘图工作台")
    win.configure(bg=COLOR_BG)
    win.geometry("1100x750")
    cp.CodePlotAppV5(win)
    win.transient(parent.winfo_toplevel())
