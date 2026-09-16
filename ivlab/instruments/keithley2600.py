"""Keithley 2600B 系列源表实现"""
from .tsp_instrument import TSPInstrument


class Keithley2600B(TSPInstrument):
    """Keithley 2600B SourceMeter - TSP/Lua 模式"""

    def __init__(self, port: str, baudrate: int = 57600, timeout: float = 5.0,
                 address: str = "smua", logger=None):
        super().__init__(port, baudrate, timeout, model="2600B", address=address, logger=logger)

    def _post_connect(self):
        super()._post_connect()
        # 2600B 初始化测量配置
        self.write(f'{self.address}.measure.count = 1')
        self.write(f'{self.address}.measure.delay = 0')
