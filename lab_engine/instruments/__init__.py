"""Lab Engine 仪器注册。

Phase 1 直接复用 ivlab 中的仪器驱动，只在这里补充引擎需要的元数据。
"""
from ivlab.instruments.cornerstone260 import Cornerstone260
from ivlab.instruments.gpd4303s import GPD4303S
from ivlab.instruments.keithley2400 import Keithley2400
from ivlab.instruments.sva1032x import SVA1032X

from lab_engine.instruments.m8190a import M8190A
from lab_engine.instruments.oscilloscope import Oscilloscope
from lab_engine.core.registry import InstrumentRegistry


InstrumentRegistry.register(
    key="cornerstone260",
    cls_type=Cornerstone260,
    name="Cornerstone 260 单色仪",
    description="Newport Cornerstone 260 单色仪，通过 DLL 控制，用于波长选择/扫描。",
    connection_params=[
        {
            "name": "dll_path",
            "label": "Cornerstone.dll 路径（需先安装 Newport Mono Utility；留空自动查找）",
            "type": "str",
            "default": "",
        },
    ],
)


InstrumentRegistry.register(
    key="sva1032x",
    cls_type=SVA1032X,
    name="Siglent SVA1032X 频谱/矢网",
    description="鼎阳 SVA1032X 频谱分析仪 / 矢量网络分析仪，VISA 连接。",
    connection_params=[
        {"name": "resource_name", "label": "VISA 资源名（留空自动发现）", "type": "str", "default": ""},
    ],
)


InstrumentRegistry.register(
    key="keithley2400",
    cls_type=Keithley2400,
    name="Keithley 2400",
    description="Keithley 2400 源表，支持 RS-232 / GPIB，可做电压/电流源与测量。",
    connection_params=[
        {"name": "port", "label": "串口 / GPIB 资源", "type": "port"},
        {"name": "baudrate", "label": "波特率", "type": "int", "default": 9600},
        {
            "name": "interface",
            "label": "接口",
            "type": "choice",
            "choices": ["rs232", "gpib"],
            "default": "rs232",
        },
    ],
)

InstrumentRegistry.register(
    key="gpd4303s",
    cls_type=GPD4303S,
    name="GPD-4303S 四通道直流电源",
    description="固纬 GPD-4303S 四通道可编程直流电源，串口控制。",
    connection_params=[
        {"name": "port", "label": "串口", "type": "port"},
        {"name": "baudrate", "label": "波特率", "type": "int", "default": 9600},
    ],
)

InstrumentRegistry.register(
    key="m8190a",
    cls_type=M8190A,
    name="Keysight M8190A AWG",
    description="Keysight M8190A 任意波形发生器，VISA 连接。",
    connection_params=[
        {"name": "visa_addr", "label": "VISA 地址", "type": "str", "default": M8190A.DEFAULT_VISA},
        {"name": "sample_rate", "label": "采样率 (Hz)", "type": "float", "default": M8190A.DEFAULT_SAMPLE_RATE},
        {"name": "vpp", "label": "输出幅度 (Vpp)", "type": "float", "default": M8190A.DEFAULT_VPP},
        {"name": "output_route", "label": "输出路径", "type": "choice", "choices": ["DC", "AC", "DAC"], "default": "DAC"},
    ],
)

InstrumentRegistry.register(
    key="oscilloscope",
    cls_type=Oscilloscope,
    name="Keysight 示波器",
    description="Keysight 示波器，VISA 连接（留空自动发现资源）。",
    connection_params=[
        {"name": "resource", "label": "VISA 资源名（留空自动发现）", "type": "str", "default": ""},
    ],
)
