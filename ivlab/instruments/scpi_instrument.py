"""SCPI 协议适配器 - 适用于 2400/2450（RS-232 版本）"""
from .base import BaseInstrument
from .scpi_mixin import SCPIMixin


class SCPIInstrument(SCPIMixin, BaseInstrument):
    """SCPI 指令集仪器基类（串口版）

    与历史版本保持兼容；SCPI 方法已抽到 SCPIMixin，可被 GPIB 等传输复用。
    """

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 5.0,
                 model: str = "", logger=None):
        super().__init__(port, baudrate, timeout, model, logger)
        self._source_mode = "voltage"
        self._measure_func = "current"

    def _post_connect(self):
        """连接后清空缓冲区并查询 IDN"""
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        super()._post_connect()
