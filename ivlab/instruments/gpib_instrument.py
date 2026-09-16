"""GPIB 协议适配器 - 基于 pyvisa + NI-VISA/Keysight VISA"""
import time
from typing import Optional

import pyvisa

from ..core.exceptions import ConnectionError, CommandError, TimeoutError
from ..core.logger import setup_logger
from .scpi_mixin import SCPIMixin


class GPIBInstrument:
    """GPIB 仪器基类

    依赖 pyvisa 与 VISA 后端（NI-VISA、Keysight VISA 或 pyvisa-py）。
    通过 GPIB 地址访问仪器，如 gpib_addr=22 -> "GPIB0::22::INSTR"。
    """

    def __init__(self, gpib_addr: int, timeout: float = 5.0,
                 model: str = "", logger=None):
        self.gpib_addr = int(gpib_addr)
        self.timeout = timeout
        self.model = model
        self.resource_name = f"GPIB0::{self.gpib_addr}::INSTR"
        self.rm: Optional[pyvisa.ResourceManager] = None
        self.inst: Optional[pyvisa.resources.GPIBInstrument] = None
        self.connected = False
        self.logger = logger or setup_logger(f"inst.{model}")
        self._debug = False

    def connect(self, retries: int = 3) -> bool:
        """连接 GPIB 仪器"""
        for attempt in range(1, retries + 1):
            try:
                self.logger.info(f"[{self.model}] 尝试连接 GPIB {self.gpib_addr} (第{attempt}次)")
                self.rm = pyvisa.ResourceManager()
                self.inst = self.rm.open_resource(self.resource_name)
                self.inst.timeout = int(self.timeout * 1000)  # ms
                # Keithley 2400 GPIB 默认终止符已合适，通常无需额外设置
                self.inst.write_termination = "\n"
                self.inst.read_termination = "\n"
                time.sleep(0.2)
                self.connected = True
                self._post_connect()
                self.logger.info(f"[{self.model}] GPIB 连接成功")
                return True
            except Exception as e:
                self.logger.warning(f"[{self.model}] 连接失败: {e}")
                self._cleanup()
                time.sleep(1)
        raise ConnectionError(f"[{self.model}] GPIB {self.gpib_addr} 连接失败，已重试{retries}次")

    def _cleanup(self):
        if self.inst is not None:
            try:
                self.inst.close()
            except Exception:
                pass
            self.inst = None
        if self.rm is not None:
            try:
                self.rm.close()
            except Exception:
                pass
            self.rm = None
        self.connected = False

    def disconnect(self):
        if self.connected:
            try:
                self._pre_disconnect()
            except Exception as e:
                self.logger.warning(f"[{self.model}] 断开前清理失败: {e}")
            finally:
                self._cleanup()
                self.logger.info(f"[{self.model}] 已断开")

    def write(self, cmd: str):
        """发送 SCPI 指令"""
        if not self.connected or self.inst is None:
            raise ConnectionError(f"[{self.model}] 未连接")
        if self._debug:
            self.logger.debug(f"[{self.model}] SEND: {cmd}")
        self.inst.write(cmd)

    def read(self, timeout: Optional[float] = None) -> str:
        """读取响应"""
        if not self.connected or self.inst is None:
            raise ConnectionError(f"[{self.model}] 未连接")
        old_timeout = None
        if timeout:
            old_timeout = self.inst.timeout
            self.inst.timeout = int(timeout * 1000)
        try:
            raw = self.inst.read()
            resp = raw.strip()
            if self._debug:
                self.logger.debug(f"[{self.model}] RECV: {resp}")
            return resp
        finally:
            if old_timeout is not None:
                self.inst.timeout = old_timeout

    def query(self, cmd: str, timeout: Optional[float] = None) -> str:
        """发送并读取"""
        if timeout:
            old_timeout = self.inst.timeout
            self.inst.timeout = int(timeout * 1000)
            try:
                return self.inst.query(cmd).strip()
            finally:
                self.inst.timeout = old_timeout
        return self.inst.query(cmd).strip()

    def reset(self):
        """复位仪器"""
        self.write("*RST")
        time.sleep(0.5)
        self.logger.info(f"[{self.model}] 已复位")

    def idn(self) -> str:
        """查询仪器标识"""
        return self.query("*IDN?")

    def check_errors(self) -> list:
        """检查错误队列，返回错误列表（默认空，SCPI mixin 会覆盖）"""
        return []

    # --- 钩子方法 ---
    def _post_connect(self):
        pass

    def _pre_disconnect(self):
        pass

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False


class GPIBSCPIInstrument(SCPIMixin, GPIBInstrument):
    """SCPI 指令集仪器基类（GPIB 版）"""

    def __init__(self, gpib_addr: int, timeout: float = 5.0,
                 model: str = "", logger=None):
        super().__init__(gpib_addr, timeout, model, logger)
        self._source_mode = "voltage"
        self._measure_func = "current"
