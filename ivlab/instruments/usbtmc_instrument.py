"""USB-TMC 协议适配器 - 基于 pyvisa + NI-VISA（USB Device 口）

部分仪器（如 Siglent SVA1000X 系列）的 USB-B Device 口不是虚拟串口，
而是 USB-TMC 设备，必须经 NI-VISA / Keysight VISA 的 USB 驱动访问，
资源名形如 "USB0::0xF4EC::0x1032::INSTR"。
"""
import time
from typing import Optional

import pyvisa

from ..core.exceptions import ConnectionError
from ..core.logger import setup_logger


class USBTMCInstrument:
    """USB-TMC 仪器基类

    依赖 pyvisa 与 VISA 后端（NI-VISA、Keysight VISA）。
    可通过 resource_name 直接指定资源，也可通过 vid 自动发现
    （列出所有 USB INSTR 资源并匹配厂商 ID）。
    """

    def __init__(self, resource_name: Optional[str] = None,
                 vid: Optional[str] = None, timeout: float = 10.0,
                 model: str = "", logger=None):
        self.resource_name = resource_name
        self.vid = vid.upper().replace("0X", "0x") if vid else None
        self.timeout = timeout
        self.model = model
        self.rm: Optional[pyvisa.ResourceManager] = None
        self.inst: Optional[pyvisa.resources.USBInstrument] = None
        self.connected = False
        self.logger = logger or setup_logger(f"inst.{model}")
        self._debug = False

    def _find_resource(self) -> str:
        """在 VISA 资源列表中发现匹配的 USB-TMC 仪器"""
        resources = self.rm.list_resources()
        usb_resources = [r for r in resources if r.upper().startswith("USB")]
        if not usb_resources:
            raise ConnectionError(
                f"[{self.model}] 未发现任何 USB-TMC 仪器，请检查 USB 连接与 NI-VISA 驱动")
        if self.vid:
            matched = [r for r in usb_resources if self.vid in r]
            if not matched:
                raise ConnectionError(
                    f"[{self.model}] 未发现 VID={self.vid} 的仪器，当前 USB 资源: {usb_resources}")
            return matched[0]
        if len(usb_resources) > 1:
            self.logger.warning(
                f"[{self.model}] 发现多个 USB 仪器 {usb_resources}，使用第一个；"
                f"建议通过 vid 或 resource_name 明确指定")
        return usb_resources[0]

    def connect(self, retries: int = 3) -> bool:
        """连接 USB-TMC 仪器"""
        for attempt in range(1, retries + 1):
            try:
                self.logger.info(f"[{self.model}] 尝试连接 USB-TMC (第{attempt}次)")
                self.rm = pyvisa.ResourceManager()
                self.resource_name = self.resource_name or self._find_resource()
                self.logger.info(f"[{self.model}] 资源: {self.resource_name}")
                self.inst = self.rm.open_resource(self.resource_name)
                self.inst.timeout = int(self.timeout * 1000)  # ms
                self.inst.write_termination = "\n"
                self.inst.read_termination = "\n"
                time.sleep(0.2)
                self.connected = True
                self._post_connect()
                self.logger.info(f"[{self.model}] USB-TMC 连接成功")
                return True
            except Exception as e:
                self.logger.warning(f"[{self.model}] 连接失败: {e}")
                self._cleanup()
                time.sleep(1)
        raise ConnectionError(f"[{self.model}] USB-TMC 连接失败，已重试{retries}次")

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
        if not self.connected or self.inst is None:
            raise ConnectionError(f"[{self.model}] 未连接")
        if self._debug:
            self.logger.debug(f"[{self.model}] SEND: {cmd}")
        old_timeout = None
        if timeout:
            old_timeout = self.inst.timeout
            self.inst.timeout = int(timeout * 1000)
        try:
            resp = self.inst.query(cmd).strip()
            if self._debug:
                self.logger.debug(f"[{self.model}] RECV: {resp[:200]}{'...' if len(resp) > 200 else ''}")
            return resp
        finally:
            if old_timeout is not None:
                self.inst.timeout = old_timeout

    def query_binary(self, cmd: str, timeout: Optional[float] = None) -> bytes:
        """发送指令并读取二进制块响应（如截图、波形数据）"""
        if timeout:
            old_timeout = self.inst.timeout
            self.inst.timeout = int(timeout * 1000)
            try:
                return bytes(self.inst.query_binary_values(cmd, datatype="s", header_fmt="empty"))
            finally:
                self.inst.timeout = old_timeout
        return bytes(self.inst.query_binary_values(cmd, datatype="s", header_fmt="empty"))

    def reset(self):
        """复位仪器"""
        self.write("*RST")
        time.sleep(0.5)
        self.logger.info(f"[{self.model}] 已复位")

    def idn(self) -> str:
        """查询仪器标识"""
        return self.query("*IDN?")

    def check_errors(self) -> list:
        """检查错误队列，返回错误列表"""
        errors = []
        for _ in range(10):  # 最多读 10 个错误
            resp = self.query(":SYST:ERR?")
            if "+0" in resp or "No error" in resp or "no error" in resp.lower():
                break
            errors.append(resp)
        return errors

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
