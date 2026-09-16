"""Cornerstone 260 单色仪 - RS-232 串口接口（ASCII 指令集）

指令集: WAVE <wl> / WAVE? / SHUTTER O|C / GRAT <n> / FILTER <n> ...
指令以回车符 (\\r) 终止，响应以 \\r\\n 结束。
"""
import time
from typing import Optional

from .base import BaseInstrument
from ..core.exceptions import ConnectionError, TimeoutError


class Monochromator(BaseInstrument):
    """单色仪基类，Cornerstone 260 RS-232 ASCII 协议

    扫描序列逻辑在 scanner/wavelength_scanner.py 中实现，
    驱动层只负责单点移动与查询。
    """

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 30.0,
                 logger=None):
        super().__init__(port, baudrate, timeout, model="CS260", logger=logger)

    # --- 通信：CS260 ASCII 指令以回车终止 ---

    def write(self, cmd: str):
        if not self.connected:
            raise ConnectionError(f"[{self.model}] 未连接")
        self.ser.write((cmd + "\r").encode("ascii"))
        if self._debug:
            self.logger.debug(f"[{self.model}] SEND: {cmd}")
        self.ser.flush()

    # --- BaseInstrument 抽象方法：单色仪作为"测量设备"的实现 ---

    def set_source_mode(self, mode: str):
        raise NotImplementedError("单色仪不支持源模式")

    def set_compliance(self, value: float):
        raise NotImplementedError("单色仪不支持合规限值")

    def set_nplc(self, nplc: float):
        raise NotImplementedError("单色仪不支持NPLC")

    def set_output_level(self, level: float):
        raise NotImplementedError("单色仪不支持输出电平")

    def measure(self) -> dict:
        """读取当前波长位置"""
        return {
            "wavelength": self.get_wavelength(),
            "timestamp": time.time(),
            "status": ""
        }

    def output_on(self):
        self.set_shutter("O")  # Open

    def output_off(self):
        self.set_shutter("C")  # Close

    def set_range(self, auto: bool, fixed_value=None):
        pass

    # --- 单色仪专用指令 ---

    def get_wavelength(self) -> float:
        return float(self.query("WAVE?"))

    def set_wavelength(self, wavelength_nm: float):
        """下发波长移动指令（不等待到位，到位查询用 goto_wavelength）"""
        self.write(f"WAVE {wavelength_nm:.3f}")

    def goto_wavelength(self, wavelength_nm: float, wait: bool = True,
                        timeout: Optional[float] = None,
                        tolerance_nm: float = 0.05) -> float:
        """移动到指定波长；wait 时轮询实际位置直到进入容差范围"""
        self.set_wavelength(wavelength_nm)
        if not wait:
            return self.get_wavelength()
        deadline = time.time() + (timeout if timeout is not None else self.timeout)
        while True:
            actual = self.get_wavelength()
            if abs(actual - wavelength_nm) <= tolerance_nm:
                return actual
            if time.time() > deadline:
                raise TimeoutError(
                    f"[{self.model}] 波长移动超时: 目标 {wavelength_nm:.3f} nm, "
                    f"当前 {actual:.3f} nm"
                )
            time.sleep(0.2)

    def set_shutter(self, state) -> bool:
        """控制快门: True/"O"/"OPEN" 打开；False/"C"/"CLOSE" 关闭"""
        if isinstance(state, str):
            cmd = state.upper()
        else:
            cmd = "O" if state else "C"
        self.write(f"SHUTTER {cmd}")
        return cmd == "O"

    def get_shutter(self) -> bool:
        """True = 快门打开"""
        return self.query("SHUTTER?").upper() == "O"

    def set_grating(self, grating: int, wait: bool = True,
                    timeout: Optional[float] = None) -> bool:
        self.write(f"GRAT {int(grating)}")
        if wait:
            deadline = time.time() + (timeout if timeout is not None else self.timeout)
            while True:
                if self.get_grating() == grating:
                    break
                if time.time() > deadline:
                    raise TimeoutError(f"[{self.model}] 光栅切换超时: {grating}")
                time.sleep(0.3)
        return True

    def get_grating(self) -> int:
        return int(float(self.query("GRAT?")))

    def set_filter(self, position: int):
        self.write(f"FILTER {int(position)}")

    def get_filter(self) -> int:
        return int(float(self.query("FILTER?")))
