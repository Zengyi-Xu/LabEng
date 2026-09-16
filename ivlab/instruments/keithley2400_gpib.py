"""Keithley 2400 源表 - GPIB 接口实现"""
from .gpib_instrument import GPIBSCPIInstrument


class Keithley2400GPIB(GPIBSCPIInstrument):
    """Keithley 2400 SourceMeter（GPIB 接口）

    用法::

        inst = Keithley2400GPIB(gpib_addr=22)
        inst.connect()
        print(inst.idn())
        inst.output_on()
        print(inst.measure())
        inst.disconnect()
    """

    def __init__(self, gpib_addr: int = 22, timeout: float = 5.0, logger=None):
        super().__init__(gpib_addr, timeout, model="2400", logger=logger)

    def _post_connect(self):
        super()._post_connect()
        # 先复位到已知默认状态，避免残留配置导致后续指令产生 -221 Settings conflict
        self.reset()
        self.set_source_mode("voltage")
        self.write(":SYST:RSEN OFF")  # 2线制测量（可改为4线制）
        self.write(":FORM:ELEM VOLT,CURR,RES,TIME,STAT")
        self.write(":TRIG:COUN 1")
        errs = self.check_errors()
        if errs:
            self.logger.warning(f"[{self.model}] 初始化后检测到错误: {errs}")
