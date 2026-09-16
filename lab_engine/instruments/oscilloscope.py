"""示波器适配器（Lab Engine 注册用）。

包装 DMT_PY_NN 中的 KeysightScopeUSB，提供符合 Lab Engine 仪器接口的类。
"""
from pathlib import Path
import sys

from ivlab.core.exceptions import ConnectionError

_DMT_PY_NN = Path(__file__).resolve().parents[3] / "DMT_PY_NN"
if _DMT_PY_NN.exists():
    sys.path.insert(0, str(_DMT_PY_NN))

try:
    from oscilloscope import KeysightScopeUSB as _KeysightScopeUSB
    HAS_DRIVER = True
except Exception:
    _KeysightScopeUSB = None
    HAS_DRIVER = False


class Oscilloscope:
    """Keysight 示波器 USB-B 的 Lab Engine 适配器。"""

    DEFAULT_RESOURCE = "USB0::0x0957::0x17A6::MY12345678::INSTR"
    DEFAULT_SAMPLE_RATE = 5e9
    DEFAULT_TIMEBASE = 150e-6

    def __init__(self, resource: str = "", timeout_ms: int = 20000):
        if not HAS_DRIVER:
            raise ImportError("未找到 DMT_PY_NN/oscilloscope.py，请确保两个仓库在同一 workspace 下")
        self._scope = _KeysightScopeUSB(
            resource=resource or self.DEFAULT_RESOURCE,
            timeout_ms=timeout_ms,
        )

    def connect(self, retries: int = 2):
        last_error = None
        for _ in range(retries):
            try:
                self._scope.connect()
                return True
            except Exception as exc:
                last_error = exc
                continue
        raise ConnectionError(f"示波器连接失败: {last_error}")

    def disconnect(self):
        self._scope.close()

    def idn(self) -> str:
        return self._scope.query("*IDN?")

    def configure(self, sample_rate=None, timebase_scale=None):
        self._scope.configure(
            sample_rate=sample_rate or self.DEFAULT_SAMPLE_RATE,
            timebase_scale=timebase_scale or self.DEFAULT_TIMEBASE,
        )

    def capture(self, channel=None, sample_rate=None, timebase_scale=None, resample_to_awg=True):
        return self._scope.capture(
            channel=channel,
            sample_rate=sample_rate,
            timebase_scale=timebase_scale,
            resample_to_awg=resample_to_awg,
        )

    def read_waveform(self, channel=None, include_preamble=True):
        return self._scope.read_waveform(channel=channel, include_preamble=include_preamble)

    def write(self, cmd: str):
        self._scope.write(cmd)

    def query(self, cmd: str) -> str:
        return self._scope.query(cmd)
