"""扫描参数配置模型"""
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class ScanConfig:
    """IV扫描配置"""
    start_v: float = 0.0          # 起始电压 (V)
    stop_v: float = 1.0           # 终止电压 (V)
    points: int = 101             # 点数
    nplc: float = 1.0             # NPLC
    compliance_i: float = 0.1     # 电流限值 (A)
    compliance_v: Optional[float] = None  # 电压限值 (V)
    source_mode: str = "voltage"  # voltage 或 current
    measure_func: str = "current" # current 或 voltage
    auto_range: bool = True
    fixed_range: Optional[float] = None
    source_delay: float = 0.0     # 源建立延迟 (s)
    output_on_before: bool = True
    output_off_after: bool = True
    n_average: int = 1            # 平均次数
    randomize_direction: bool = False  # 随机化扫描方向
    scan_type: str = "single"     # single, double, sweep (0->Vmax->0->-Vmax->0)

    # Trigger Link 外部触发/触发输出（仅 Keithley 2400 系列）
    external_trigger: bool = False        # 作为从机：等待 Trigger Link 输入
    output_trigger: bool = False          # 作为主机：从 Trigger Link 输出触发
    trigger_source: str = "IMM"           # 触发源：IMM/TLIN/TIM/MAN/BUS
    trigger_count: int = 1                # 触发计数
    trigger_output: str = "NONE"          # Trigger Out：SOUR/SENS/DEL/NONE
    trigger_delay: float = 0.0            # 触发延迟（s）
    external_trigger_timeout: float = 30.0  # 等待外部触发时的串口超时（s）

    def __post_init__(self):
        if self.points < 2:
            raise ValueError("points必须>=2")
        if self.n_average < 1:
            raise ValueError("n_average必须>=1")


@dataclass
class InstrumentConfig:
    """仪器连接配置"""
    port: str = "COM1"
    baudrate: int = 9600
    timeout: float = 5.0
    model: str = "2400"  # 2400, 2450, 2600B
    address: str = "smua"  # 2600B通道地址
