"""IV 扫描引擎"""
import time
import numpy as np
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass

from ..core.config import ScanConfig
from ..core.exceptions import ScanError, TimeoutError
from ..core.logger import setup_logger
from ..instruments.base import BaseInstrument


@dataclass
class ScanResult:
    """单次扫描结果"""
    voltages: np.ndarray
    currents: np.ndarray
    resistances: np.ndarray
    timestamps: np.ndarray
    direction: str  # "forward" 或 "backward"
    metadata: dict


class IVScanner:
    """IV 曲线扫描器"""

    def __init__(self, instrument: BaseInstrument, config: ScanConfig, logger=None):
        self.instrument = instrument
        self.config = config
        self.logger = logger or setup_logger("scanner")
        self.results: List[ScanResult] = []
        self._stop_flag = False
        self._original_timeout: Optional[float] = None

    def setup_instrument(self):
        """配置仪器参数"""
        cfg = self.config
        inst = self.instrument

        inst.reset()
        time.sleep(0.3)

        # 设置源模式（内部会自动打开源量程自动、关闭并发测量并选择互补测功能）
        inst.set_source_mode(cfg.source_mode)
        time.sleep(0.1)

        # 设置测量功能（与源模式互补：电压源测电流，电流源测电压）
        if hasattr(inst, "set_measure_function"):
            measure_func = "current" if cfg.source_mode == "voltage" else "voltage"
            inst.set_measure_function(measure_func)

        # 先设置量程（自动或固定），再设置合规限值；
        # 否则在固定小量程下设置大合规值会触发 -221 Settings conflict
        inst.set_range(cfg.auto_range, cfg.fixed_range)

        # 设置合规限值
        inst.set_compliance(cfg.compliance_i)

        # 设置NPLC
        inst.set_nplc(cfg.nplc)

        # 设置源延迟
        if hasattr(inst, "set_source_delay"):
            inst.set_source_delay(cfg.source_delay)

        # Trigger Link 触发配置（从机等待触发 / 主机输出触发）
        if cfg.external_trigger or cfg.output_trigger or cfg.trigger_output != "NONE":
            if hasattr(inst, "set_trigger_source"):
                # 从机模式强制使用 TLIN；主机模式使用 IMM（或用户指定）
                trigger_source = "TLIN" if cfg.external_trigger else cfg.trigger_source
                trigger_output = cfg.trigger_output
                if cfg.output_trigger and trigger_output == "NONE":
                    trigger_output = "SENS"  # 默认在测量完成后输出触发脉冲

                inst.set_trigger_source(trigger_source)
                inst.set_trigger_count(cfg.trigger_count)
                inst.set_trigger_output(trigger_output)
                inst.set_trigger_delay(cfg.trigger_delay)

                if cfg.external_trigger:
                    # 延长串口超时，避免等待外部触发时过早返回空
                    self._original_timeout = getattr(inst, "timeout", None)
                    inst.timeout = cfg.external_trigger_timeout
                    if hasattr(inst, "ser") and inst.ser is not None:
                        inst.ser.timeout = cfg.external_trigger_timeout

                self.logger.info(
                    f"Trigger Link 已配置: source={trigger_source}, "
                    f"count={cfg.trigger_count}, output={trigger_output}, "
                    f"delay={cfg.trigger_delay}s"
                    + (f", timeout={cfg.external_trigger_timeout}s" if cfg.external_trigger else "")
                )
            else:
                self.logger.warning("当前仪器不支持 Trigger Link 触发配置，已忽略")

        # 清掉配置过程中可能产生的任何单条 warning，避免污染后续查询
        errs = inst.check_errors() if hasattr(inst, "check_errors") else []
        if errs:
            self.logger.warning(f"仪器配置后错误队列: {errs}")

        self.logger.info(f"仪器配置完成: {cfg.source_mode}源, NPLC={cfg.nplc}, "
                        f"合规={cfg.compliance_i}A, 量程自动={cfg.auto_range}")

    def _generate_voltages(self, direction: str = "forward") -> np.ndarray:
        """生成电压序列"""
        cfg = self.config

        if cfg.scan_type == "single":
            v = np.linspace(cfg.start_v, cfg.stop_v, cfg.points)
        elif cfg.scan_type == "double":
            v_fwd = np.linspace(cfg.start_v, cfg.stop_v, cfg.points)
            v_bwd = np.linspace(cfg.stop_v, cfg.start_v, cfg.points)
            if direction == "forward":
                v = v_fwd
            else:
                v = v_bwd
        elif cfg.scan_type == "sweep":
            # 0 -> Vmax -> 0 -> -Vmax -> 0
            v1 = np.linspace(0, cfg.stop_v, cfg.points)
            v2 = np.linspace(cfg.stop_v, 0, cfg.points)
            v3 = np.linspace(0, -cfg.stop_v, cfg.points)
            v4 = np.linspace(-cfg.stop_v, 0, cfg.points)
            v = np.concatenate([v1, v2[1:], v3[1:], v4[1:]])
        else:
            raise ScanError(f"不支持的扫描类型: {cfg.scan_type}")

        return v

    def _run_single_scan(self, direction: str = "forward") -> ScanResult:
        """执行单次扫描"""
        inst = self.instrument
        cfg = self.config
        voltages = self._generate_voltages(direction)

        n = len(voltages)
        currents = np.zeros(n)
        resistances = np.zeros(n)
        timestamps = np.zeros(n)

        self.logger.info(f"开始{direction}扫描: {voltages[0]:.3f}V -> {voltages[-1]:.3f}V, {n}点")

        # 开启输出
        if cfg.output_on_before:
            inst.output_on()
            time.sleep(0.2)

        t_start = time.time()
        i = -1

        for i, v in enumerate(voltages):
            if self._stop_flag:
                self.logger.warning("扫描被用户中断")
                break

            # 设置电压
            inst.set_output_level(v)

            # 源建立延迟
            if cfg.source_delay > 0:
                time.sleep(cfg.source_delay)

            # 测量
            try:
                data = inst.measure()
                currents[i] = data["current"]
                resistances[i] = data.get("resistance", 0)
                timestamps[i] = time.time() - t_start

                # 溢出检测
                if abs(currents[i]) > 9.9e37:
                    self.logger.warning(f"点{i} 电流溢出 (9.91E37)")
                    currents[i] = np.nan

                # 合规性检查
                if abs(currents[i]) >= cfg.compliance_i * 0.99:
                    self.logger.warning(f"点{i} 接近合规限值: I={currents[i]:.3e}A")

            except Exception as e:
                self.logger.error(f"点{i} 测量失败: {e}")
                currents[i] = np.nan
                resistances[i] = np.nan

        # 关闭输出
        if cfg.output_off_after:
            inst.output_off()

        elapsed = time.time() - t_start
        self.logger.info(f"扫描完成: {n}点, 耗时{elapsed:.2f}s, 平均{n/elapsed:.1f}点/秒")

        return ScanResult(
            voltages=voltages[:i+1] if self._stop_flag else voltages,
            currents=currents[:i+1] if self._stop_flag else currents,
            resistances=resistances[:i+1] if self._stop_flag else resistances,
            timestamps=timestamps[:i+1] if self._stop_flag else timestamps,
            direction=direction,
            metadata={
                "nplc": cfg.nplc,
                "compliance": cfg.compliance_i,
                "source_delay": cfg.source_delay,
                "scan_type": cfg.scan_type,
                "elapsed_time": elapsed
            }
        )

    def _restore_timeout(self):
        """恢复原始串口超时"""
        if self._original_timeout is None:
            return
        inst = self.instrument
        if hasattr(inst, "timeout"):
            inst.timeout = self._original_timeout
        if hasattr(inst, "ser") and inst.ser is not None:
            inst.ser.timeout = self._original_timeout
        self._original_timeout = None
        self.logger.debug("串口超时已恢复")

    def run(self, progress_callback: Optional[Callable] = None) -> List[ScanResult]:
        """执行完整扫描（含多次平均）"""
        self.results = []
        cfg = self.config

        try:
            self.setup_instrument()

            for avg_idx in range(cfg.n_average):
                self.logger.info(f"===== 第 {avg_idx+1}/{cfg.n_average} 次扫描 =====")

                # 确定方向
                if cfg.randomize_direction and avg_idx % 2 == 1:
                    direction = "backward"
                else:
                    direction = "forward"

                result = self._run_single_scan(direction)
                self.results.append(result)

                if progress_callback:
                    progress_callback(avg_idx + 1, cfg.n_average, result)

                if self._stop_flag:
                    break

                # 扫描间隔
                if avg_idx < cfg.n_average - 1:
                    time.sleep(0.5)
        finally:
            self._restore_timeout()

        return self.results

    def stop(self):
        """停止扫描"""
        self._stop_flag = True
        self.logger.info("收到停止信号")

    def get_averaged_result(self) -> Optional[ScanResult]:
        """获取平均后的结果"""
        if not self.results:
            return None

        # 统一插值到相同电压网格
        all_v = [r.voltages for r in self.results]
        all_i = [r.currents for r in self.results]

        # 使用第一个扫描的电压网格作为参考
        v_grid = self.results[0].voltages
        i_interp = []

        for v, i in zip(all_v, all_i):
            # 线性插值
            i_grid = np.interp(v_grid, v, i, left=np.nan, right=np.nan)
            i_interp.append(i_grid)

        i_avg = np.nanmean(i_interp, axis=0)

        return ScanResult(
            voltages=v_grid,
            currents=i_avg,
            resistances=np.zeros_like(v_grid),  # 平均后重新计算
            timestamps=self.results[0].timestamps,
            direction="averaged",
            metadata={"n_average": len(self.results)}
        )
