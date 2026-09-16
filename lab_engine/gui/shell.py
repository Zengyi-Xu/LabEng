"""GUI 外壳工具：DPI 适配、中文字体、ttk 主题、通用容器。"""
import ctypes
import sys
import tkinter as tk
from tkinter import ttk

import matplotlib
import matplotlib.font_manager as fm

matplotlib.use("TkAgg")


# ── 配色 ────────────────────────────────────────────────────────────────────
COLOR_BG = "#F3F5F7"          # 窗口底色（浅灰）
COLOR_CARD = "#FFFFFF"        # 卡片白
COLOR_BORDER = "#E2E8F0"      # 卡片描边
COLOR_PRIMARY = "#164E63"     # 主色（深青）
COLOR_PRIMARY_HOVER = "#0E7490"
COLOR_TEXT = "#1F2937"        # 主文字
COLOR_TEXT_DIM = "#64748B"    # 次要文字
COLOR_DANGER = "#B91C1C"
COLOR_SELECT = "#164E63"


# ── DPI 适配 ─────────────────────────────────────────────────────────────────

def set_dpi_aware():
    """让 Windows 按真实 DPI 渲染，避免高分屏下界面过小或模糊。"""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def get_system_dpi() -> int:
    """获取系统主屏 DPI。"""
    if sys.platform != "win32":
        return 96
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return dpi
    except Exception:
        return 96


def set_tk_scaling(root: tk.Tk) -> float:
    """根据 DPI 设置 tk scaling，返回缩放比例。"""
    dpi = get_system_dpi()
    scale = dpi / 96.0
    try:
        root.tk.call("tk", "scaling", dpi / 72.0)
    except Exception:
        pass
    return max(scale, 1.0)


# ── 字体 ─────────────────────────────────────────────────────────────────────

def pick_font(candidates):
    """返回 candidates 中系统上第一个可用的字体。"""
    available = {f.name for f in fm.fontManager.ttflist}
    for name in candidates:
        if name in available:
            return name
    return candidates[-1] if candidates else "DejaVu Sans"


def setup_plot_fonts():
    """设置 matplotlib 中文字体。"""
    candidates = [
        "Microsoft YaHei", "SimHei", "SimSun", "STSong",
        "WenQuanYi Micro Hei", "Noto Sans CJK SC", "Source Han Sans SC",
    ]
    chosen = pick_font(candidates)
    matplotlib.rcParams["font.sans-serif"] = [chosen] + ["DejaVu Sans"]
    matplotlib.rcParams["axes.unicode_minus"] = False


UI_FONT = pick_font(["Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "DejaVu Sans", "Liberation Sans"])
MONO_FONT = pick_font(["Consolas", "Liberation Mono", "DejaVu Sans Mono", "Courier"])


# ── 样式配置 ─────────────────────────────────────────────────────────────────

def configure_styles(root: tk.Tk, scale: float):
    """配置统一 ttk 主题。"""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    font_base = (UI_FONT, 10)
    font_bold = (UI_FONT, 10, "bold")
    font_tab = (UI_FONT, 11)
    pad_x = int(round(14 * scale))
    pad_y = int(round(8 * scale))

    style.configure(".", font=font_base, background=COLOR_BG, foreground=COLOR_TEXT)

    style.configure("TFrame", background=COLOR_BG)
    style.configure("Card.TFrame", background=COLOR_CARD)
    style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT)
    style.configure("Card.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT)
    style.configure("Dim.TLabel", background=COLOR_BG, foreground=COLOR_TEXT_DIM)
    style.configure("DimCard.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT_DIM)
    style.configure("Title.TLabel", background=COLOR_BG, foreground=COLOR_PRIMARY,
                    font=(UI_FONT, 17, "bold"))
    style.configure("Subtitle.TLabel", background=COLOR_BG, foreground=COLOR_TEXT_DIM,
                    font=(UI_FONT, 10))
    style.configure("Section.TLabel", background=COLOR_CARD, foreground=COLOR_PRIMARY,
                    font=font_bold)
    style.configure("Pill.TLabel", background=COLOR_PRIMARY, foreground="#FFFFFF",
                    font=font_bold, padding=(pad_x, int(round(4 * scale))))
    style.configure("Metrics.TLabel", background=COLOR_BG, foreground=COLOR_PRIMARY_HOVER,
                    font=font_bold)

    style.configure("TNotebook", background=COLOR_BG, borderwidth=0)
    style.configure("TNotebook.Tab", font=font_tab, padding=(pad_x + 6, pad_y),
                    background="#E5EAEF", foreground=COLOR_TEXT)
    style.map("TNotebook.Tab",
              background=[("selected", COLOR_CARD)],
              foreground=[("selected", COLOR_PRIMARY)])

    style.configure("Accent.TButton", font=font_bold, padding=(pad_x, pad_y),
                    background=COLOR_PRIMARY, foreground="#FFFFFF",
                    borderwidth=0, focusthickness=0)
    style.map("Accent.TButton",
              background=[("active", COLOR_PRIMARY_HOVER), ("disabled", "#9FB3BC")],
              foreground=[("disabled", "#E5EAEF")])

    style.configure("TButton", font=font_base, padding=(pad_x, pad_y),
                    background="#E5EAEF", foreground=COLOR_TEXT, borderwidth=0)
    style.map("TButton", background=[("active", "#D5DDE4")])

    style.configure("Danger.TButton", font=font_bold, padding=(pad_x, pad_y),
                    background=COLOR_DANGER, foreground="#FFFFFF",
                    borderwidth=0)
    style.map("Danger.TButton",
              background=[("active", "#DC2626"), ("disabled", "#D1A5A5")])

    indicator = int(round(13 * scale))
    style.configure("TRadiobutton", background=COLOR_CARD, foreground=COLOR_TEXT,
                    font=font_base, indicatorsize=indicator)
    style.configure("TCheckbutton", background=COLOR_CARD, foreground=COLOR_TEXT,
                    font=font_base, indicatorsize=indicator)
    style.configure("TLabelframe", background=COLOR_CARD, bordercolor=COLOR_BORDER)
    style.configure("TLabelframe.Label", background=COLOR_CARD, foreground=COLOR_PRIMARY,
                    font=font_bold)

    style.configure("TCombobox", padding=(int(round(8 * scale)), int(round(4 * scale))))

    style.configure("Treeview", background=COLOR_CARD, fieldbackground=COLOR_CARD,
                    foreground=COLOR_TEXT, rowheight=int(round(28 * scale)),
                    font=font_base, borderwidth=0)
    style.configure("Treeview.Heading", background="#EEF2F5", foreground=COLOR_PRIMARY,
                    font=font_bold, padding=(int(round(6 * scale)), int(round(6 * scale))))
    style.map("Treeview",
              background=[("selected", COLOR_SELECT)],
              foreground=[("selected", "#FFFFFF")])

    style.configure("TSeparator", background=COLOR_BORDER)
    # 滚动条加粗到约 3 倍，便于触摸/鼠标拖拽
    sb_width = int(round(36 * scale))
    style.configure("Vertical.TScrollbar", background="#D5DDE4", troughcolor=COLOR_BG,
                    borderwidth=0, arrowsize=int(round(18 * scale)), width=sb_width)
    style.configure("Horizontal.TScrollbar", background="#D5DDE4", troughcolor=COLOR_BG,
                    borderwidth=0, arrowsize=int(round(18 * scale)), width=sb_width)


def make_card(parent, **pack_kwargs):
    """创建带细边框的白色卡片容器。"""
    card = tk.Frame(parent, bg=COLOR_CARD,
                    highlightbackground=COLOR_BORDER, highlightthickness=1, bd=0)
    if pack_kwargs:
        card.pack(**pack_kwargs)
    return card


def dpi_scale(pixels: int, scale: float) -> int:
    """按缩放比例转换像素尺寸。"""
    return int(pixels * scale)
