"""Keithley 2400 软件模拟器。

用于在没有真实仪器的情况下离线验证 IVScanner、DataHandler、
HysteresisAnalyzer 以及 Lab Engine 例程的执行流程。

用法::

    from ivlab.instruments.mock_keithley2400 import MockKeithley2400
    from ivlab.core.config import ScanConfig
    from ivlab.scanner.iv_scanner import IVScanner

    inst = MockKeithley2400()
    inst.connect()
    scanner = IVScanner(inst, ScanConfig(start_v=0, stop_v=2, points=51))
    results = scanner.run()
    inst.disconnect()
"""
import time
import numpy as np
from typing import Optional

from .scpi_instrument import SCPIInstrument


class MockKeithley2400(SCPIInstrument):
    """Keithley 2400 的软件替身。

    不打开真实串口，所有 SCPI 命令在内存中解析并返回仿真响应。
    默认仿真一个非线性二极管-like 器件：
        I = I0 * (exp(V / (n*Vt)) - 1) + V / R_shunt + noise
    """

    IDN = "KEITHLEY INSTRUMENTS INC.,MODEL 2400,MOCK0001,C30 Mock 2026"

    def __init__(
        self,
        port: str = "MOCK",
        baudrate: int = 9600,
        timeout: float = 5.0,
        logger=None,
        scale: float = 1e-3,
        nonlin: float = 0.3,
        r_shunt: float = 1e5,
        noise: float = 1e-9,
        hysteresis: float = 0.15,
    ):
        # 绕过 BaseInstrument.__init__ 不保存 serial 对象，手动设置必要属性
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.model = "2400-MOCK"
        from ..core.logger import setup_logger

        self.logger = logger or setup_logger(f"inst.{self.model}")
        self.ser = None
        self.connected = False
        self._debug = False

        self._source_mode = "voltage"
        self._measure_func = "current"
        self._output_level = 0.0
        self._compliance = 0.1
        self._output_on = False
        self._last_cmd = ""

        # 器件模型参数
        self._scale = scale          # 饱和电流幅值 (A)
        self._nonlin = nonlin        # tanh 的非线性尺度 (V)
        self._r_shunt = r_shunt      # 并联电阻 (Ohm)
        self._noise = noise          # 电流噪声 (A rms)
        self._hysteresis = hysteresis  # 回滞幅度 (比例)

        # 用于产生回滞：记录上一次输出电平
        self._last_level = 0.0

    # --- 连接管理（不操作真实硬件） ---

    def connect(self, retries: int = 3) -> bool:
        self.connected = True
        self._post_connect()
        self.logger.info(f"[{self.model}] Mock 连接成功")
        return True

    def _post_connect(self):
        """覆盖 SCPIInstrument._post_connect，避免访问 self.ser。"""
        self.reset()
        self.set_source_mode("voltage")
        self.write(":SYST:RSEN OFF")
        self.write(":FORM:ELEM VOLT,CURR,RES,TIME,STAT")
        self.write(":TRIG:COUN 1")

    def disconnect(self):
        if self.connected:
            self._output_on = False
            self.connected = False
            self.logger.info(f"[{self.model}] Mock 已断开")

    # --- 底层通信 ---

    def write(self, cmd: str):
        if not self.connected:
            raise ConnectionError(f"[{self.model}] 未连接")
        self._last_cmd = cmd.strip()
        if self._debug:
            self.logger.debug(f"[{self.model}] SEND: {cmd}")

    def read(self, timeout: Optional[float] = None) -> str:
        if not self.connected:
            raise ConnectionError(f"[{self.model}] 未连接")
        return ""

    def query(self, cmd: str, timeout: Optional[float] = None) -> str:
        self.write(cmd)
        return self._handle_query(cmd.strip())

    def reset(self):
        self._source_mode = "voltage"
        self._measure_func = "current"
        self._output_level = 0.0
        self._last_level = 0.0
        self._scan_direction = 0
        self._compliance = 0.1
        self._output_on = False
        time.sleep(0.05)

    def idn(self) -> str:
        return self.IDN

    # --- 仪器功能（记录状态） ---

    def output_on(self):
        self._output_on = True
        self.logger.debug(f"[{self.model}] 输出开启")

    def output_off(self):
        self._output_on = False
        self.logger.debug(f"[{self.model}] 输出关闭")

    def set_output_level(self, level: float):
        level = float(level)
        # 根据电压变化方向判断当前扫描方向
        if level > self._last_level + 1e-9:
            self._scan_direction = 1
        elif level < self._last_level - 1e-9:
            self._scan_direction = -1
        # 否则保持上一次方向
        self._last_level = level
        self._output_level = level

    # --- 仿真响应生成 ---

    def _handle_query(self, cmd: str) -> str:
        cmd = cmd.strip()
        upper = cmd.upper()

        if upper == "*IDN?":
            return self.IDN

        if upper == ":SYST:ERR?" or upper == "SYST:ERR?":
            return "+0,\"No error\""

        if upper == ":READ?" or upper == "READ?":
            return self._simulate_read()

        # 解析 SET/LEV 命令，记录输出电平
        if upper.startswith(":SOUR:VOLT:LEV") or upper.startswith("SOUR:VOLT:LEV"):
            self._output_level = self._parse_last_value(cmd)
            return ""
        if upper.startswith(":SOUR:CURR:LEV") or upper.startswith("SOUR:CURR:LEV"):
            self._output_level = self._parse_last_value(cmd)
            return ""

        # 其他写命令直接返回空响应
        return ""

    @staticmethod
    def _parse_last_value(cmd: str) -> float:
        parts = cmd.split()
        return float(parts[-1]) if parts else 0.0

    def _simulate_read(self) -> str:
        """生成一次 :READ? 的返回：voltage,current,resistance,time,status。"""
        if not self._output_on:
            v = 0.0
            i = 0.0
        elif self._source_mode == "voltage":
            v = self._output_level
            i = self._device_current(v, direction=getattr(self, "_scan_direction", 0))
        else:  # current source
            i = self._output_level
            # 简单反解：I = f(V)，这里近似 V = I * R 串联
            v = self._solve_voltage(i)

        r = v / i if abs(i) > 1e-15 else 1e18
        t = time.time()
        status = "0"
        return f"{v:.6e},{i:.6e},{r:.6e},{t:.6f},{status}"

    def _device_current(self, v: float, direction: int = 0) -> float:
        """仿真器件电流。

        基础模型: I = scale * tanh(V / nonlin) + V / r_shunt
        加入方向相关回滞，使 forward / backward 两条曲线可分开。
        """
        i_base = self._scale * np.tanh(v / self._nonlin) + v / self._r_shunt

        # 回滞项：与扫描方向成正比
        if direction > 0:
            i_hyst = self._hysteresis * self._scale * (1.0 - np.tanh(abs(v) / self._nonlin))
        elif direction < 0:
            i_hyst = -self._hysteresis * self._scale * (1.0 - np.tanh(abs(v) / self._nonlin))
        else:
            i_hyst = 0.0

        i = i_base + i_hyst
        if self._noise > 0:
            i += np.random.normal(0.0, self._noise)
        return float(i)

    def _solve_voltage(self, i: float) -> float:
        """给定电流，数值求解电压（用于电流源模式）。"""
        # 简单牛顿迭代，回滞项设为 0 近似
        v = i * self._r_shunt
        for _ in range(20):
            f = self._device_current(v, direction=0) - i
            df = (
                self._scale / self._nonlin * (1.0 / np.cosh(v / self._nonlin) ** 2)
                + 1.0 / self._r_shunt
            )
            if abs(df) < 1e-18:
                break
            dv = f / df
            v -= dv
            if abs(dv) < 1e-9:
                break
        return float(v)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False
