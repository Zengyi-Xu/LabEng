"""GW Instek GPD-4303S 四通道可编程直流电源驱动。

后面板 USB-B Device 口在 Windows 上会被识别为虚拟 COM 口，
因此直接用 pyserial 即可控制。命令以 ``\\n`` 终止，响应以 ``\\r\\n`` 或 ``\\n`` 结束。
"""
import re
import time
from typing import Any, Dict, Optional

from ..core.exceptions import ConnectionError, CommandError
from ..core.logger import setup_logger


class GPD4303S:
    """GW Instek GPD-4303S 四通道直流电源驱动。"""

    CHANNELS = (1, 2, 3, 4)
    VOLTAGE_RANGES = {
        1: (0.0, 32.0),
        2: (0.0, 32.0),
        3: (2.5, 5.5),   # CH3 为固定低压通道
        4: (0.0, 15.0),
    }
    CURRENT_RANGES = {
        1: (0.0, 3.0),
        2: (0.0, 3.0),
        3: (0.0, 1.0),
        4: (0.0, 1.0),
    }

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 5.0, logger=None):
        try:
            import serial
        except ImportError as exc:
            raise ConnectionError(
                "使用 GPD-4303S 需要 pyserial。安装命令：pip install pyserial>=3.5"
            ) from exc
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser: Optional[Any] = None
        self.connected = False
        self.logger = logger or setup_logger("inst.gpd4303s")
        self._debug = False

    # --- 连接管理 --------------------------------------------------------
    def connect(self, retries: int = 3) -> bool:
        """连接仪器，支持重试。"""
        import serial
        for attempt in range(1, retries + 1):
            try:
                self.logger.info(f"[GPD-4303S] 尝试连接 {self.port} (第 {attempt} 次)")
                self.ser = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=self.timeout,
                    xonxoff=False,
                    rtscts=False,
                )
                self.ser.setRTS(True)
                self.ser.setDTR(True)
                time.sleep(0.5)
                self.connected = True
                self._post_connect()
                self.logger.info("[GPD-4303S] 连接成功")
                return True
            except Exception as e:
                self.logger.warning(f"[GPD-4303S] 连接失败: {e}")
                if attempt < retries:
                    time.sleep(1)
        raise ConnectionError(f"[GPD-4303S] 连接 {self.port} 失败，已重试 {retries} 次")

    def disconnect(self):
        """断开连接，安全关闭输出。"""
        if self.connected and self.ser is not None:
            try:
                self.output_off()
            except Exception as e:
                self.logger.warning(f"[GPD-4303S] 关闭输出失败: {e}")
            try:
                if self.ser.is_open:
                    self.ser.close()
            except Exception as e:
                self.logger.warning(f"[GPD-4303S] 关闭串口失败: {e}")
            finally:
                self.connected = False
                self.logger.info("[GPD-4303S] 已断开")

    def _post_connect(self):
        """连接后清空缓冲区、进入远程模式并唤醒命令解析器。"""
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        self.write("REMOTE")
        time.sleep(0.1)
        # 部分固件的第一条查询会返回空，先发一次 *IDN? 做“热身”，忽略响应
        self.query("*IDN?")

    # --- 底层通信 --------------------------------------------------------
    def write(self, cmd: str):
        """发送指令。"""
        if not self.connected or self.ser is None:
            raise ConnectionError("[GPD-4303S] 未连接")
        full_cmd = cmd + "\n"
        self.ser.write(full_cmd.encode("ascii"))
        if self._debug:
            self.logger.debug(f"[GPD-4303S] SEND: {cmd}")
        self.ser.flush()

    def read(self, timeout: Optional[float] = None) -> str:
        """读取一行响应。"""
        if not self.connected or self.ser is None:
            raise ConnectionError("[GPD-4303S] 未连接")
        old_timeout = self.ser.timeout
        if timeout:
            self.ser.timeout = timeout
        try:
            raw = self.ser.readline()
            resp = raw.decode("ascii", errors="replace").strip()
            if self._debug:
                self.logger.debug(f"[GPD-4303S] RECV: {resp}")
            return resp
        finally:
            if timeout:
                self.ser.timeout = old_timeout

    def query(self, cmd: str, timeout: Optional[float] = None) -> str:
        """发送指令并读取响应（自动跳过可能的命令回显）。"""
        self.write(cmd)
        deadline = time.monotonic() + (timeout or self.timeout or 5.0)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return ""
            resp = self.read(timeout=remaining)
            if not resp:
                return ""
            if resp.strip() == cmd.strip():
                continue
            return resp

    # --- 仪器功能 --------------------------------------------------------
    def idn(self) -> str:
        """查询仪器标识。"""
        return self.query("*IDN?")

    def set_voltage(self, channel: int, voltage: float):
        """设置指定通道的输出电压。"""
        self._check_channel(channel)
        self.write(f"VSET{channel}:{voltage:.3f}")

    def set_current(self, channel: int, current: float):
        """设置指定通道的输出电流。"""
        self._check_channel(channel)
        self.write(f"ISET{channel}:{current:.3f}")

    def get_voltage_set(self, channel: int) -> float:
        """查询指定通道的电压设定值。"""
        self._check_channel(channel)
        return self._parse_value(self.query(f"VSET{channel}?"))

    def get_current_set(self, channel: int) -> float:
        """查询指定通道的电流设定值。"""
        self._check_channel(channel)
        return self._parse_value(self.query(f"ISET{channel}?"))

    def measure_voltage(self, channel: int) -> float:
        """读取指定通道的实际输出电压。"""
        self._check_channel(channel)
        return self._parse_value(self.query(f"VOUT{channel}?"))

    def measure_current(self, channel: int) -> float:
        """读取指定通道的实际输出电流。"""
        self._check_channel(channel)
        return self._parse_value(self.query(f"IOUT{channel}?"))

    def output_on(self):
        """打开总输出（OUT1）。"""
        self.write("OUT1")

    def output_off(self):
        """关闭总输出（OUT0）。"""
        self.write("OUT0")

    def beep(self, on: bool = True):
        """打开或关闭蜂鸣器。"""
        self.write(f"BEEP{1 if on else 0}")

    def local(self):
        """让仪器返回本地（面板）控制模式。"""
        self.write("LOCAL")

    def remote(self):
        """进入远程控制模式。"""
        self.write("REMOTE")

    def get_status(self) -> Dict[str, Any]:
        """读取 STATUS? 并解析为字典。

        GPD-X303S 返回的 STATUS? 是一个 8 位 0/1 字符串，前 4 位通常依次对应
        CH1~CH4 的 CV/CC 状态（1=CV，0=CC），其余位为蜂鸣器、总输出、追踪模式
        等状态。若返回格式不符，则按整数的二进制位兜底解析。
        """
        raw = self.query("STATUS?")
        modes: Dict[int, Optional[str]] = {}

        if len(raw) >= 4 and all(c in ("0", "1") for c in raw[:4]):
            for i, ch in enumerate(self.CHANNELS):
                modes[ch] = "CV" if raw[i] == "1" else "CC"
        elif raw.isdigit():
            val = int(raw)
            for i, ch in enumerate(self.CHANNELS):
                modes[ch] = "CV" if (val >> i) & 1 else "CC"
        else:
            for ch in self.CHANNELS:
                modes[ch] = None

        return {"raw": raw, "channel_modes": modes}

    def measure_all(self) -> Dict[str, Any]:
        """读取所有四个通道的实际电压、电流和 CV/CC 状态。"""
        ts = time.time()
        status = self.get_status()
        voltage = {}
        current = {}
        for ch in self.CHANNELS:
            try:
                voltage[ch] = self.measure_voltage(ch)
            except Exception as e:
                voltage[ch] = None
                self.logger.warning(f"[GPD-4303S] 读取 CH{ch} 电压失败: {e}")
            try:
                current[ch] = self.measure_current(ch)
            except Exception as e:
                current[ch] = None
                self.logger.warning(f"[GPD-4303S] 读取 CH{ch} 电流失败: {e}")

        return {
            "voltage": voltage,
            "current": current,
            "mode": status.get("channel_modes", {}),
            "status_raw": status.get("raw", ""),
            "timestamp": ts,
        }

    # --- 内部辅助 --------------------------------------------------------
    @staticmethod
    def _parse_value(resp: str) -> float:
        """解析仪器返回的带单位数值，如 '3.300V' -> 3.3。"""
        resp = resp.strip()
        m = re.match(r"^\s*([+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)", resp)
        if not m:
            raise CommandError(f"[GPD-4303S] 无法解析仪器返回值: {resp!r}")
        return float(m.group(1))

    def _check_channel(self, channel: int):
        if channel not in self.CHANNELS:
            raise CommandError(f"[GPD-4303S] 通道 {channel} 无效，应为 1~4")

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
        return False
