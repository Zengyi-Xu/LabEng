"""波长扫描引擎 - 驱动单色仪执行波长扫描

扫描序列属于上层编排逻辑，统一放在 scanner 层实现；
instruments 层的驱动只提供单点移动 (goto_wavelength) 与查询。
"""
import time
import numpy as np
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass, field

from ..core.exceptions import ScanError, TimeoutError
from ..core.logger import setup_logger


@dataclass
class WavelengthScanConfig:
    """波长扫描配置"""
    start_nm: float = 400.0         # 起始波长 (nm)
    stop_nm: float = 700.0          # 终止波长 (nm)
    step_nm: float = 1.0            # 波长步长 (nm)
    settle_timeout_s: float = 60.0  # 单点到位超时 (s)
    settle_tolerance_nm: float = 0.05  # 到位判定容差 (nm)
    dwell_s: float = 0.0            # 到位后额外驻留时间 (s)
    scan_type: str = "single"       # single 或 double（往返）
    open_shutter: bool = True       # 扫描开始时自动打开快门
    close_shutter_after: bool = False  # 扫描结束后关闭快门

    def __post_init__(self):
        if self.step_nm <= 0:
            raise ValueError("step_nm必须>0")
        if self.scan_type not in ("single", "double"):
            raise ValueError("scan_type必须是 single 或 double")


@dataclass
class WavelengthScanResult:
    """单次波长扫描结果"""
    wavelengths: np.ndarray      # 请求波长 (nm)
    actual: np.ndarray           # 实际到位波长 (nm)
    powers: Optional[np.ndarray]  # 功率计读数（无功率计时为 None）
    timestamps: np.ndarray       # 各点时间戳 (s)
    direction: str               # "forward" 或 "backward"
    metadata: dict = field(default_factory=dict)


class WavelengthScanner:
    """波长扫描器

    可选配光功率计，在每个波长点同步读取功率，构成光谱扫描::

        scanner = WavelengthScanner(mono, config, power_meter=pm)
        results = scanner.run(progress_callback=cb)
    """

    def __init__(self, monochromator, config: WavelengthScanConfig,
                 power_meter=None, logger=None):
        self.mono = monochromator
        self.config = config
        self.power_meter = power_meter
        self.logger = logger or setup_logger("scanner")
        self.results: List[WavelengthScanResult] = []

    def _generate_grid(self, direction: str) -> np.ndarray:
        cfg = self.config
        n = int(round(abs(cfg.stop_nm - cfg.start_nm) / cfg.step_nm)) + 1
        grid = cfg.start_nm + np.arange(n) * cfg.step_nm * (1 if cfg.stop_nm >= cfg.start_nm else -1)
        if direction == "backward":
            grid = grid[::-1]
        return grid

    def _run_direction(self, direction: str,
                       progress_callback: Optional[Callable] = None) -> WavelengthScanResult:
        cfg = self.config
        grid = self._generate_grid(direction)

        actual = np.zeros(len(grid))
        powers = np.zeros(len(grid)) if self.power_meter is not None else None
        timestamps = np.zeros(len(grid))

        self.logger.info(f"开始波长扫描 [{direction}]: "
                         f"{grid[0]:.2f} -> {grid[-1]:.2f} nm, {len(grid)} 点")

        for i, wl in enumerate(grid):
            t0 = time.time()
            try:
                pos = self.mono.goto_wavelength(
                    wl, wait=True,
                    timeout=cfg.settle_timeout_s,
                    tolerance_nm=cfg.settle_tolerance_nm)
            except TimeoutError:
                raise ScanError(f"波长 {wl:.2f} nm 移动超时，扫描中止")
            if cfg.dwell_s > 0:
                time.sleep(cfg.dwell_s)

            actual[i] = pos
            timestamps[i] = time.time()
            if powers is not None:
                reading = self.power_meter.measure()
                powers[i] = float(reading.get("power", np.nan))

            if progress_callback:
                progress_callback(i + 1, len(grid), wl,
                                  powers[i] if powers is not None else None)

        self.logger.info(f"波长扫描 [{direction}] 完成，耗时 {time.time() - timestamps[0]:.1f}s")

        return WavelengthScanResult(
            wavelengths=grid,
            actual=actual,
            powers=powers,
            timestamps=timestamps,
            direction=direction,
            metadata={
                "start_nm": cfg.start_nm,
                "stop_nm": cfg.stop_nm,
                "step_nm": cfg.step_nm,
                "dwell_s": cfg.dwell_s,
                "scan_type": cfg.scan_type,
            }
        )

    def run(self, progress_callback: Optional[Callable] = None) -> List[WavelengthScanResult]:
        """执行扫描，返回各方向的结果列表"""
        cfg = self.config
        self.results = []

        if cfg.open_shutter:
            self.mono.output_on()
            self.logger.info("快门已打开")

        try:
            self.results.append(self._run_direction("forward", progress_callback))
            if cfg.scan_type == "double":
                self.results.append(self._run_direction("backward", progress_callback))
        finally:
            if cfg.close_shutter_after:
                self.mono.output_off()
                self.logger.info("快门已关闭")

        return self.results

    def get_averaged_result(self) -> Optional[WavelengthScanResult]:
        """多方向扫描时，按请求波长对齐取平均功率"""
        if not self.results:
            return None
        if len(self.results) == 1:
            return self.results[0]

        ref = self.results[0]
        avg_powers = ref.powers.copy() if ref.powers is not None else None
        for r in self.results[1:]:
            if avg_powers is not None and r.powers is not None:
                avg_powers += r.powers
        if avg_powers is not None:
            avg_powers /= len(self.results)

        return WavelengthScanResult(
            wavelengths=ref.wavelengths,
            actual=ref.actual,
            powers=avg_powers,
            timestamps=ref.timestamps,
            direction="averaged",
            metadata={**ref.metadata, "n_scans": len(self.results)}
        )
