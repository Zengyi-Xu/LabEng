"""TSP (Test Script Processor) 协议适配器 - 适用于 2600B 系列"""
import time
from typing import Optional
from .base import BaseInstrument
from ..core.exceptions import CommandError


class TSPInstrument(BaseInstrument):
    """TSP/Lua 脚本仪器基类，适用于 Keithley 2600B"""

    def __init__(self, port: str, baudrate: int = 57600, timeout: float = 5.0,
                 model: str = "2600B", address: str = "smua", logger=None):
        super().__init__(port, baudrate, timeout, model, logger)
        self.address = address  # smua 或 smub
        self._source_mode = "voltage"

    def _post_connect(self):
        """连接后清空缓冲区"""
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()
        # 2600B 默认就是 TSP 模式，无需切换
        self.logger.info(f"[{self.model}] TSP 模式已就绪，通道: {self.address}")

    def _tsp_cmd(self, cmd: str) -> str:
        """包装 TSP 指令，自动添加通道前缀"""
        # 如果指令已经包含 smua/smub，则不添加前缀
        if "smu" not in cmd.lower():
            return f"{self.address}.{cmd}"
        return cmd

    def set_source_mode(self, mode: str):
        """设置源模式"""
        mode = mode.lower()
        if mode == "voltage":
            self.write(f'{self.address}.source.func = {self.address}.OUTPUT_DCVOLTS')
            self._source_mode = "voltage"
        elif mode == "current":
            self.write(f'{self.address}.source.func = {self.address}.OUTPUT_DCAMPS')
            self._source_mode = "current"
        else:
            raise ConfigurationError(f"不支持的源模式: {mode}")
        self.logger.debug(f"[{self.model}] 源模式设为 {mode}")

    def set_compliance(self, value: float):
        """设置合规限值"""
        if self._source_mode == "voltage":
            self.write(f'{self.address}.source.limiti = {value}')
        else:
            self.write(f'{self.address}.source.limitv = {value}')
        self.logger.debug(f"[{self.model}] 合规限值设为 {value}")

    def set_nplc(self, nplc: float):
        """设置NPLC"""
        self.write(f'{self.address}.measure.nplc = {nplc}')
        self.logger.debug(f"[{self.model}] NPLC设为 {nplc}")

    def set_output_level(self, level: float):
        """设置输出电平"""
        if self._source_mode == "voltage":
            self.write(f'{self.address}.source.levelv = {level}')
        else:
            self.write(f'{self.address}.source.leveli = {level}')

    def measure(self) -> dict:
        """执行测量，返回电压、电流、电阻、时间"""
        # TSP 返回单个值，需要分别读取
        # 先读电压
        self.write(f'print({self.address}.measure.v())')
        time.sleep(0.05)
        v_str = self.read()
        # 读电流
        self.write(f'print({self.address}.measure.i())')
        time.sleep(0.05)
        i_str = self.read()
        # 读电阻
        self.write(f'print({self.address}.measure.r())')
        time.sleep(0.05)
        r_str = self.read()

        try:
            voltage = float(v_str) if v_str else float("nan")
            current = float(i_str) if i_str else float("nan")
            resistance = float(r_str) if r_str else float("nan")
        except ValueError:
            raise CommandError(f"TSP测量返回异常: V={v_str}, I={i_str}, R={r_str}")

        return {
            "voltage": voltage,
            "current": current,
            "resistance": resistance,
            "timestamp": time.time(),
            "status": ""
        }

    def output_on(self):
        self.write(f'{self.address}.source.output = {self.address}.OUTPUT_ON')
        self.logger.debug(f"[{self.model}] 输出开启")

    def output_off(self):
        self.write(f'{self.address}.source.output = {self.address}.OUTPUT_OFF')
        self.logger.debug(f"[{self.model}] 输出关闭")

    def set_range(self, auto: bool, fixed_value: Optional[float] = None):
        """设置量程"""
        if auto:
            self.write(f'{self.address}.measure.autorangei = {self.address}.AUTORANGE_ON')
        elif fixed_value is not None:
            self.write(f'{self.address}.measure.rangei = {fixed_value}')

    def reset(self):
        """TSP 复位"""
        self.write("reset()")
        time.sleep(1.0)  # TSP reset 需要更长时间
        self.logger.info(f"[{self.model}] TSP 复位完成")

    def idn(self) -> str:
        """TSP 查询标识"""
        self.write("print(localnode.model)")
        time.sleep(0.1)
        model = self.read()
        self.write("print(localnode.serialno)")
        time.sleep(0.1)
        sn = self.read()
        return f"{model},{sn}"

    def check_errors(self) -> list:
        """TSP 错误检查"""
        errors = []
        self.write("print(errorqueue.count)")
        time.sleep(0.05)
        count_str = self.read()
        try:
            count = int(float(count_str)) if count_str else 0
        except ValueError:
            count = 0
        for _ in range(min(count, 10)):
            self.write("print(errorqueue.next())")
            time.sleep(0.05)
            err = self.read()
            if err and "0\tNo error" not in err:
                errors.append(err)
        return errors
