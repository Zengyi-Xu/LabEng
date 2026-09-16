"""SCPI 指令集 Mixin - 与具体通信方式解耦

依赖子类提供：
    - connect()
    - disconnect()
    - write(cmd)
    - read(timeout)
    - query(cmd, timeout)
    - reset()
    - idn()
    - logger
    - model
"""
from typing import Optional

from ..core.exceptions import ConfigurationError, CommandError, ConnectionError


class SCPIMixin:
    """SCPI 通用指令集实现，可被 Serial/GPIB/Ethernet 等传输层复用"""

    _source_mode: str = "voltage"
    _measure_func: str = "current"

    @staticmethod
    def _func_to_scpi(func: str) -> str:
        """把内部 'current'/'voltage' 映射为 Keithley 接受的短格式 'CURR'/'VOLT'."""
        return {"current": "CURR", "voltage": "VOLT"}.get(func.lower(), func.upper())

    def _post_connect(self):
        """连接后清空缓冲区并查询 IDN"""
        idn = self.idn()
        if not idn:
            raise ConnectionError(
                f"[{self.model}] 未收到 *IDN? 响应，请检查线缆/波特率/握手线")
        self.logger.info(f"[{self.model}] IDN: {idn}")

    def set_source_mode(self, mode: str):
        """设置源模式（测量功能自动切换为与源互补的另一端：电压源测电流，电流源测电压）"""
        mode = mode.lower()
        if mode == "voltage":
            self.write(":SOUR:FUNC VOLT")
            self._source_mode = "voltage"
            self._measure_func = "current"
        elif mode == "current":
            self.write(":SOUR:FUNC CURR")
            self._source_mode = "current"
            self._measure_func = "voltage"
        else:
            raise ConfigurationError(f"不支持的源模式: {mode}")
        scpi_source = self._func_to_scpi(mode)
        # 先打开源量程自动，避免后面设源电平超出当前固定量程；再关闭并发测量并选单功能
        self.write(f":SOUR:{scpi_source}:RANG:AUTO ON")
        self.write(":SENS:FUNC:CONC OFF")
        self.write(f':SENS:FUNC "{self._func_to_scpi(self._measure_func)}"')
        self.logger.debug(f"[{self.model}] 源模式设为 {mode}")

    def set_compliance(self, value: float):
        """设置合规限值"""
        if self._source_mode == "voltage":
            self.write(f":SENS:CURR:PROT {value}")
        else:
            self.write(f":SENS:VOLT:PROT {value}")
        self.logger.debug(f"[{self.model}] 合规限值设为 {value}")

    def set_nplc(self, nplc: float):
        """设置 NPLC"""
        if self._measure_func == "current":
            self.write(f":SENS:CURR:NPLC {nplc}")
        elif self._measure_func == "voltage":
            self.write(f":SENS:VOLT:NPLC {nplc}")
        else:
            self.write(f":SENS:CURR:NPLC {nplc}")
        self.logger.debug(f"[{self.model}] NPLC 设为 {nplc}")

    def set_output_level(self, level: float):
        """设置输出电平"""
        if self._source_mode == "voltage":
            self.write(f":SOUR:VOLT:LEV {level}")
        else:
            self.write(f":SOUR:CURR:LEV {level}")

    def measure(self) -> dict:
        """执行测量，返回电压、电流、电阻、时间"""
        resp = self.query(":READ?")
        # 2400 返回格式: voltage,current,resistance,time,status
        parts = resp.split(",")
        if len(parts) >= 4:
            return {
                "voltage": float(parts[0]),
                "current": float(parts[1]),
                "resistance": float(parts[2]),
                "timestamp": float(parts[3]),
                "status": parts[4] if len(parts) > 4 else ""
            }
        raise CommandError(f"测量返回格式异常: {resp}")

    def output_on(self):
        self.write(":OUTP ON")
        self.logger.debug(f"[{self.model}] 输出开启")

    def output_off(self):
        self.write(":OUTP OFF")
        self.logger.debug(f"[{self.model}] 输出关闭")

    def set_range(self, auto: bool, fixed_value: Optional[float] = None):
        """设置量程"""
        func = "CURR" if self._measure_func == "current" else "VOLT"
        if auto:
            self.write(f":SENS:{func}:RANG:AUTO ON")
        elif fixed_value is not None:
            self.write(f":SENS:{func}:RANG {fixed_value}")
            self.write(f":SENS:{func}:RANG:AUTO OFF")

    def set_measure_function(self, func: str):
        """设置测量功能（必须与源模式互补，不允许测量与源相同的物理量）"""
        func = func.lower()
        if func == self._source_mode:
            raise ConfigurationError(
                f"测量功能不能等于源模式: 当前为{self._source_mode}源，"
                f"只能测量{'电压' if self._source_mode == 'current' else '电流'}"
            )
        if func == "current":
            self.write(':SENS:FUNC "CURR"')
            self._measure_func = "current"
        elif func == "voltage":
            self.write(':SENS:FUNC "VOLT"')
            self._measure_func = "voltage"
        else:
            raise ConfigurationError(f"不支持的测量功能: {func}")

    def check_errors(self) -> list:
        """检查错误队列"""
        errors = []
        for _ in range(10):  # 最多读 10 个错误
            resp = self.query(":SYST:ERR?")
            if "+0" in resp or "No error" in resp:
                break
            errors.append(resp)
        return errors

    # ------------------------------------------------------------------
    # Trigger Link 外部触发
    # ------------------------------------------------------------------
    def set_trigger_source(self, source: str):
        """设置触发源：IMM/TLIN/TIM/MAN/BUS（2400 后面板 Trigger Link 用 TLIN）"""
        source = source.upper()
        if source not in {"IMM", "TLIN", "TIM", "MAN", "BUS"}:
            raise ConfigurationError(f"不支持的触发源: {source}")
        self.write(f":TRIG:SOUR {source}")
        self.logger.debug(f"[{self.model}] 触发源设为 {source}")

    def set_trigger_count(self, count):
        """设置触发计数；逐点外部同步时设为 1"""
        self.write(f":TRIG:COUN {count}")
        self.logger.debug(f"[{self.model}] 触发计数设为 {count}")

    def set_trigger_output(self, event: str):
        """设置 Trigger Out 输出时机：SOUR/SENS/DEL/NONE"""
        event = event.upper()
        if event not in {"SOUR", "SENS", "DEL", "NONE"}:
            raise ConfigurationError(f"不支持的触发输出: {event}")
        self.write(f":TRIG:OUTP {event}")
        self.logger.debug(f"[{self.model}] 触发输出设为 {event}")

    def set_trigger_delay(self, delay: float):
        """设置触发到达后的延迟（秒）"""
        self.write(f":TRIG:DEL {delay}")
        self.logger.debug(f"[{self.model}] 触发延迟设为 {delay}s")

    def init_measurement(self):
        """启动测量并进入等待触发状态（配合 TLIN 使用）"""
        self.write(":INIT")

    def fetch(self) -> str:
        """取回已完成的测量结果（配合 :INIT 使用）"""
        return self.query(":FETC?")
