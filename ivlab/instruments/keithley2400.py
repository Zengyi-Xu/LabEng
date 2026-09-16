"""Keithley 2400 源表实现"""
from .scpi_instrument import SCPIInstrument


class Keithley2400(SCPIInstrument):
    """Keithley 2400 SourceMeter"""

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 5.0, logger=None):
        super().__init__(port, baudrate, timeout, model="2400", logger=logger)

    def _post_connect(self):
        super()._post_connect()
        # 先复位到已知默认状态，避免残留配置导致后续指令产生 -221 Settings conflict
        self.reset()
        # 显式设为电压源/测电流，确保 :FORM:ELEM 的每个元素都合法
        self.set_source_mode("voltage")
        self.write(":SYST:RSEN OFF")  # 2线制测量（可改为4线制）
        self.write(":FORM:ELEM VOLT,CURR,RES,TIME,STAT")
        self.write(":TRIG:COUN 1")
        errs = self.check_errors()
        if errs:
            self.logger.warning(f"[{self.model}] 初始化后检测到错误: {errs}")
