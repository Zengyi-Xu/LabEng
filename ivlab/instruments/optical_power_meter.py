"""Newport 2359-R 光功率计 - 预留接口"""
from .base import BaseInstrument


class OpticalPowerMeter(BaseInstrument):
    """光功率计基类，预留 Newport 2359-R 接口"""

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 5.0, logger=None):
        super().__init__(port, baudrate, timeout, model="2359-R", logger=logger)

    def set_source_mode(self, mode: str):
        raise NotImplementedError("光功率计不支持源模式设置")

    def set_compliance(self, value: float):
        raise NotImplementedError("光功率计不支持合规限值")

    def set_nplc(self, nplc: float):
        raise NotImplementedError("光功率计不支持NPLC")

    def set_output_level(self, level: float):
        raise NotImplementedError("光功率计不支持输出电平")

    def measure(self) -> dict:
        """读取光功率值 (dBm 或 W)"""
        # TODO: 实现 2359-R 具体协议
        # 典型指令: "READ?" 或 "MEAS:POW?"
        resp = self.query("READ?")
        return {
            "power": float(resp),
            "unit": "dBm",  # 或 W
            "timestamp": 0,
            "status": ""
        }

    def output_on(self):
        pass

    def output_off(self):
        pass

    def set_range(self, auto: bool, fixed_value=None):
        pass

    def set_wavelength(self, wavelength_nm: float):
        """设置校准波长"""
        self.write(f"WAVELENGTH {wavelength_nm}")

    def set_unit(self, unit: str):
        """设置单位: DBM 或 W"""
        self.write(f"UNIT {unit.upper()}")
