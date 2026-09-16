"""回滞分析模块"""
import numpy as np
from typing import List, Dict, Tuple
from dataclasses import dataclass

from .iv_scanner import ScanResult
from ..core.logger import setup_logger


@dataclass
class HysteresisResult:
    """回滞分析结果"""
    forward_v: np.ndarray
    forward_i: np.ndarray
    backward_v: np.ndarray
    backward_i: np.ndarray
    delta_i: np.ndarray           # 同一电压下电流差值
    delta_i_max: float            # 最大电流差值
    hysteresis_area: float        # 回滞环面积 (V·A)
    hysteresis_index: float       # 回滞指数 = max|ΔI| / max|I|
    symmetry_factor: float        # 对称因子
    voltage_grid: np.ndarray      # 统一电压网格

    def to_dict(self) -> dict:
        return {
            "delta_i_max": self.delta_i_max,
            "hysteresis_area": self.hysteresis_area,
            "hysteresis_index": self.hysteresis_index,
            "symmetry_factor": self.symmetry_factor,
            "n_points": len(self.voltage_grid)
        }


class HysteresisAnalyzer:
    """回滞分析器"""

    def __init__(self, logger=None):
        self.logger = logger or setup_logger("hysteresis")

    def analyze(self, forward_result: ScanResult, 
                backward_result: ScanResult) -> HysteresisResult:
        """分析正向和反向扫描的回滞特性"""

        # 提取数据
        v_fwd = forward_result.voltages
        i_fwd = forward_result.currents
        v_bwd = backward_result.voltages
        i_bwd = backward_result.currents

        # 若反向扫描电压为递减，需先反转使其单调递增，
        # 否则 np.interp 会按错误顺序插值
        if len(v_bwd) > 1 and v_bwd[-1] < v_bwd[0]:
            v_bwd = v_bwd[::-1]
            i_bwd = i_bwd[::-1]

        # 创建统一电压网格（取交集范围）
        v_min = max(v_fwd.min(), v_bwd.min())
        v_max = min(v_fwd.max(), v_bwd.max())
        v_grid = np.linspace(v_min, v_max, max(len(v_fwd), len(v_bwd)))

        # 插值到统一网格
        i_fwd_grid = np.interp(v_grid, v_fwd, i_fwd, left=np.nan, right=np.nan)
        i_bwd_grid = np.interp(v_grid, v_bwd, i_bwd, left=np.nan, right=np.nan)

        # 计算差值
        delta_i = i_bwd_grid - i_fwd_grid

        # 移除NaN
        valid = ~(np.isnan(i_fwd_grid) | np.isnan(i_bwd_grid))
        v_valid = v_grid[valid]
        delta_i_valid = delta_i[valid]
        i_fwd_valid = i_fwd_grid[valid]
        i_bwd_valid = i_bwd_grid[valid]

        if len(v_valid) < 3:
            self.logger.warning("有效数据点过少，无法计算回滞")
            return HysteresisResult(
                forward_v=v_fwd, forward_i=i_fwd,
                backward_v=v_bwd, backward_i=i_bwd,
                delta_i=np.array([]), delta_i_max=0,
                hysteresis_area=0, hysteresis_index=0,
                symmetry_factor=0, voltage_grid=v_grid
            )

        # 计算指标
        delta_i_max = np.max(np.abs(delta_i_valid))

        # 回滞面积（数值积分，梯形法则）
        hysteresis_area = np.trapezoid(np.abs(delta_i_valid), v_valid)

        # 回滞指数
        i_max = max(np.max(np.abs(i_fwd_valid)), np.max(np.abs(i_bwd_valid)))
        hysteresis_index = delta_i_max / i_max if i_max > 0 else 0

        # 对称因子（正向与反向曲线积分面积比）
        area_fwd = np.trapezoid(np.abs(i_fwd_valid), v_valid)
        area_bwd = np.trapezoid(np.abs(i_bwd_valid), v_valid)
        symmetry_factor = area_bwd / area_fwd if area_fwd > 0 else 0

        self.logger.info(f"回滞分析: 面积={hysteresis_area:.3e}, 指数={hysteresis_index:.4f}, "
                        f"最大ΔI={delta_i_max:.3e}, 对称因子={symmetry_factor:.3f}")

        return HysteresisResult(
            forward_v=v_fwd, forward_i=i_fwd,
            backward_v=v_bwd, backward_i=i_bwd,
            delta_i=delta_i_valid,
            delta_i_max=delta_i_max,
            hysteresis_area=hysteresis_area,
            hysteresis_index=hysteresis_index,
            symmetry_factor=symmetry_factor,
            voltage_grid=v_valid
        )

    def analyze_double_scan(self, results: List[ScanResult]) -> List[HysteresisResult]:
        """分析多次双扫的结果列表"""
        hysteresis_list = []

        # 配对正向和反向扫描
        i = 0
        while i < len(results) - 1:
            if results[i].direction == "forward" and results[i+1].direction == "backward":
                h = self.analyze(results[i], results[i+1])
                hysteresis_list.append(h)
                i += 2
            else:
                i += 1

        return hysteresis_list

    def average_hysteresis(self, h_list: List[HysteresisResult]) -> Dict:
        """平均多个回滞分析结果"""
        if not h_list:
            return {}

        areas = [h.hysteresis_area for h in h_list]
        indices = [h.hysteresis_index for h in h_list]
        max_deltas = [h.delta_i_max for h in h_list]

        return {
            "hysteresis_area_mean": np.mean(areas),
            "hysteresis_area_std": np.std(areas),
            "hysteresis_index_mean": np.mean(indices),
            "hysteresis_index_std": np.std(indices),
            "delta_i_max_mean": np.mean(max_deltas),
            "delta_i_max_std": np.std(max_deltas),
            "n_scans": len(h_list)
        }
