"""多仪器协调器"""
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from ..core.logger import setup_logger
from ..instruments.base import BaseInstrument


@dataclass
class ScanStep:
    """扫描步骤定义"""
    instrument_name: str
    action: str  # "set_wavelength", "iv_scan", "read_power", "wait", "set_voltage"
    params: dict
    wait_after: float = 0.0  # 执行后等待时间 (s)


@dataclass
class CoordinatedData:
    """多仪器协调数据点"""
    timestamp: float
    values: Dict[str, Any]  # {instrument_name: measurement_dict}
    step_index: int


class MultiInstrumentCoordinator:
    """多仪器协调扫描器"""

    def __init__(self, logger=None):
        self.instruments: Dict[str, BaseInstrument] = {}
        self.logger = logger or setup_logger("coordinator")
        self.data: List[CoordinatedData] = []

    def add_instrument(self, name: str, instrument: BaseInstrument):
        """添加仪器到协调器"""
        self.instruments[name] = instrument
        self.logger.info(f"添加仪器: {name} ({instrument.model})")

    def connect_all(self):
        """连接所有仪器"""
        for name, inst in self.instruments.items():
            if not inst.connected:
                inst.connect()
                self.logger.info(f"{name} 已连接")

    def disconnect_all(self):
        """断开所有仪器"""
        for name, inst in self.instruments.items():
            inst.disconnect()
        self.logger.info("所有仪器已断开")

    def run_sequence(self, steps: List[ScanStep], 
                     progress_callback=None) -> List[CoordinatedData]:
        """执行多仪器协调扫描序列"""
        self.data = []
        t_start = time.time()

        for idx, step in enumerate(steps):
            self.logger.info(f"步骤 {idx+1}/{len(steps)}: {step.instrument_name}.{step.action}")

            point = CoordinatedData(
                timestamp=time.time() - t_start,
                values={},
                step_index=idx
            )

            # 执行动作
            if step.action == "wait":
                wait_time = step.params.get("seconds", 0)
                time.sleep(wait_time)

            elif step.action == "iv_scan":
                # 执行IV扫描（简化版，实际应调用IVScanner）
                inst = self.instruments.get(step.instrument_name)
                if inst:
                    # 这里简化处理，实际应调用 IVScanner
                    point.values[step.instrument_name] = {"action": "iv_scan_done"}

            elif step.action == "set_wavelength":
                inst = self.instruments.get(step.instrument_name)
                if inst and hasattr(inst, "set_wavelength"):
                    wl = step.params.get("wavelength", 500)
                    inst.set_wavelength(wl)
                    point.values[step.instrument_name] = {"wavelength": wl}

            elif step.action == "read_power":
                inst = self.instruments.get(step.instrument_name)
                if inst:
                    data = inst.measure()
                    point.values[step.instrument_name] = data

            elif step.action == "set_voltage":
                inst = self.instruments.get(step.instrument_name)
                if inst:
                    v = step.params.get("voltage", 0)
                    inst.set_output_level(v)
                    point.values[step.instrument_name] = {"voltage_set": v}

            # 记录所有仪器当前读数（可选）
            if step.params.get("read_all", False):
                for name, inst in self.instruments.items():
                    if name not in point.values and inst.connected:
                        try:
                            point.values[name] = inst.measure()
                        except Exception as e:
                            self.logger.warning(f"读取 {name} 失败: {e}")

            self.data.append(point)

            # 等待
            if step.wait_after > 0:
                time.sleep(step.wait_after)

            if progress_callback:
                progress_callback(idx + 1, len(steps), point)

        self.logger.info(f"序列完成: {len(steps)} 步骤, {len(self.data)} 数据点")
        return self.data

    def parallel_read(self, instrument_names: List[str]) -> Dict[str, Any]:
        """并行读取多台仪器（顺序执行，但统一时间戳）"""
        t = time.time()
        results = {}
        for name in instrument_names:
            inst = self.instruments.get(name)
            if inst and inst.connected:
                try:
                    results[name] = inst.measure()
                except Exception as e:
                    self.logger.warning(f"并行读取 {name} 失败: {e}")
                    results[name] = None
        return {"timestamp": t, "values": results}
