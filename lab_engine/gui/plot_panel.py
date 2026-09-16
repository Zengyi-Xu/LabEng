"""实时数据曲线面板（支持多曲线分组）。"""
import tkinter as tk
from typing import Any, Dict, List, Optional

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from lab_engine.gui.shell import COLOR_CARD


# 曲线颜色池
_SERIES_COLORS = [
    "#3B82F6", "#EF4444", "#10B981", "#F59E0B", "#8B5CF6",
    "#EC4899", "#14B8A6", "#F97316", "#6366F1", "#84CC16",
]

_MAX_POINTS_PER_SERIES = 5000


class PlotPanel(tk.Frame):
    """基于 matplotlib 的实时曲线面板。"""

    def __init__(self, parent):
        super().__init__(parent, bg=COLOR_CARD)
        self.series_data: Dict[str, List[Dict[str, Any]]] = {}
        self.series_colors: Dict[str, str] = {}
        self.x_key: Optional[str] = None
        self.y_key: Optional[str] = None
        self._next_color_idx = 0
        self._setup_ui()

    def _setup_ui(self):
        self.fig = Figure(figsize=(6, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_title("等待数据...")
        self.ax.grid(True, alpha=0.3)
        self.fig.tight_layout()

        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.toolbar = NavigationToolbar2Tk(self.canvas, self)
        self.toolbar.update()

    def clear(self):
        """清空数据。"""
        self.series_data.clear()
        self.series_colors.clear()
        self._next_color_idx = 0
        self.x_key = None
        self.y_key = None
        self.ax.clear()
        self.ax.set_title("等待数据...")
        self.ax.grid(True, alpha=0.3)
        self.canvas.draw_idle()

    def _get_series_color(self, series: str) -> str:
        if series not in self.series_colors:
            self.series_colors[series] = _SERIES_COLORS[
                self._next_color_idx % len(_SERIES_COLORS)
            ]
            self._next_color_idx += 1
        return self.series_colors[series]

    def add_point(self, **kwargs: Any):
        """添加一个数据点并尝试自动绘图。"""
        series = str(kwargs.pop("series", "default"))
        if series not in self.series_data:
            self.series_data[series] = []
        self.series_data[series].append(dict(kwargs))
        self._auto_select_axes()
        # 抽稀：单 series 超过限制时随机保留
        if len(self.series_data[series]) > _MAX_POINTS_PER_SERIES:
            self.series_data[series] = _downsample(self.series_data[series])
        total = sum(len(v) for v in self.series_data.values())
        if self.x_key and self.y_key and total % 3 == 0:
            self._redraw()

    def add_points(self, points: List[Dict[str, Any]]):
        """批量添加数据点。"""
        for p in points:
            series = str(p.get("series", "default"))
            if series not in self.series_data:
                self.series_data[series] = []
            self.series_data[series].append(dict(p))
        # 抽稀
        for series in list(self.series_data.keys()):
            if len(self.series_data[series]) > _MAX_POINTS_PER_SERIES:
                self.series_data[series] = _downsample(self.series_data[series])
        self._auto_select_axes()
        if self.x_key and self.y_key:
            self._redraw()

    def _auto_select_axes(self):
        """根据数据自动选择 x/y 列。"""
        if not self.series_data:
            return
        # 取第一个 series 的第一个点
        first_series = next(iter(self.series_data.values()))
        if not first_series:
            return
        keys = list(first_series[0].keys())
        numeric_keys = [
            k for k in keys
            if isinstance(first_series[0].get(k), (int, float, np.number))
        ]
        if len(numeric_keys) < 2:
            return

        # 常见 I-V 扫描：优先 voltage / current
        if "voltage" in numeric_keys and "current" in numeric_keys:
            self.x_key = "voltage"
            self.y_key = "current"
        elif "wavelength" in numeric_keys and "current" in numeric_keys:
            self.x_key = "wavelength"
            self.y_key = "current"
        elif "wavelength" in numeric_keys and "power" in numeric_keys:
            self.x_key = "wavelength"
            self.y_key = "power"
        elif "x" in numeric_keys and "y" in numeric_keys:
            self.x_key = "x"
            self.y_key = "y"
        else:
            self.x_key = numeric_keys[0]
            self.y_key = numeric_keys[1]

    def _redraw(self):
        """重绘曲线。"""
        if not self.x_key or not self.y_key:
            return

        self.ax.clear()
        for series, data in self.series_data.items():
            xs = [
                p.get(self.x_key) for p in data
                if isinstance(p.get(self.x_key), (int, float, np.number))
            ]
            ys = [
                p.get(self.y_key) for p in data
                if isinstance(p.get(self.y_key), (int, float, np.number))
            ]
            if len(xs) < 2:
                continue
            color = self._get_series_color(series)
            self.ax.plot(xs, ys, color=color, markersize=3, linewidth=1,
                         label=series, marker="o", linestyle="-")

        self.ax.set_xlabel(self.x_key)
        self.ax.set_ylabel(self.y_key)
        self.ax.set_title(f"{self.y_key} vs {self.x_key}")
        self.ax.grid(True, alpha=0.3)
        if len(self.series_data) > 1:
            self.ax.legend(loc="best", fontsize=8)
        self.fig.tight_layout()
        self.canvas.draw_idle()

    def set_labels(self, xlabel: str, ylabel: str, title: str):
        """手动设置坐标轴标签。"""
        self.ax.set_xlabel(xlabel)
        self.ax.set_ylabel(ylabel)
        self.ax.set_title(title)
        self.canvas.draw_idle()


def _downsample(points: List[Dict[str, Any]], max_points: int = _MAX_POINTS_PER_SERIES) -> List[Dict[str, Any]]:
    """等间隔抽稀数据点，保持时间顺序。"""
    if len(points) <= max_points:
        return points
    step = len(points) / max_points
    indices = [int(i * step) for i in range(max_points)]
    indices[-1] = len(points) - 1  # 保留最后一个点
    return [points[i] for i in indices]
