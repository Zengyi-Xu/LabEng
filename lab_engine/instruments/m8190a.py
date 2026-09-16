"""M8190A AWG 适配器（Lab Engine 注册用）。

包装 DMT_PY_NN 中的 M8190AController，提供符合 Lab Engine 仪器接口的类。
"""
from pathlib import Path
import sys

from ivlab.core.exceptions import ConnectionError

# 允许 lab_engine 访问 DMT_PY_NN 中的驱动（如果两个仓库在同一 workspace 下）
_DMT_PY_NN = Path(__file__).resolve().parents[3] / "DMT_PY_NN"
if _DMT_PY_NN.exists():
    sys.path.insert(0, str(_DMT_PY_NN))

try:
    from awg_m8190a import M8190AController as _M8190AController
    HAS_DRIVER = True
except Exception:
    _M8190AController = None
    HAS_DRIVER = False


class M8190A:
    """M8190A AWG 的 Lab Engine 适配器。"""

    DEFAULT_VISA = "TCPIP0::localhost::5025::SOCKET"
    DEFAULT_SAMPLE_RATE = 2.0e9
    DEFAULT_VPP = 0.7

    def __init__(self, visa_addr: str = "", sample_rate: float = 2.0e9,
                 vpp: float = 0.7, output_route: str = "DAC", timeout_ms: int = 30000):
        if not HAS_DRIVER:
            raise ImportError("未找到 DMT_PY_NN/awg_m8190a.py，请确保两个仓库在同一 workspace 下")
        self._ctrl = _M8190AController(
            visa_addr=visa_addr or self.DEFAULT_VISA,
            sample_rate=sample_rate,
            vpp=vpp,
            output_route=output_route,
            timeout_ms=timeout_ms,
        )

    def connect(self, retries: int = 2):
        last_error = None
        for _ in range(retries):
            try:
                self._ctrl.connect()
                return True
            except Exception as exc:
                last_error = exc
                continue
        raise ConnectionError(f"M8190A 连接失败: {last_error}")

    def disconnect(self):
        self._ctrl.close()

    def idn(self) -> str:
        return self._ctrl.query("*IDN?")

    def configure(self, **kwargs):
        self._ctrl.configure(**kwargs)

    def download_waveform(self, data, channel=1, segment=1, run=True):
        self._ctrl.download_waveform(data, channel=channel, segment=segment, run=run)

    def download_iq(self, iqdata, channel_i=1, channel_q=2, segment=1, run=True):
        self._ctrl.download_iq(iqdata, channel_i=channel_i, channel_q=channel_q, segment=segment, run=run)

    def stop(self, channels=(1, 2)):
        self._ctrl.stop(channels)

    def write(self, cmd: str):
        self._ctrl.write(cmd)

    def query(self, cmd: str) -> str:
        return self._ctrl.query(cmd)
