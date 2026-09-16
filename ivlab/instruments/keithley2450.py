"""Keithley 2450 源表实现 (2400 SCPI 兼容模式)"""
from .scpi_instrument import SCPIInstrument


class Keithley2450(SCPIInstrument):
    """Keithley 2450 SourceMeter - 使用2400兼容SCPI模式"""

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 5.0, logger=None):
        super().__init__(port, baudrate, timeout, model="2450", logger=logger)

    def _post_connect(self):
        super()._post_connect()
        # 2450 切换到 2400 兼容模式
        self.write(":SYST:LANG SCPI2400")
        import time
        time.sleep(0.5)
        self.write(":FORM:ELEM VOLT,CURR,RES,TIME,STAT")
        self.logger.info("[2450] 已切换到 SCPI2400 兼容模式")
