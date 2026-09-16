"""基础 IV 扫描例程。

Keithley 2400 作为电压源执行单向/双向/往返 IV 扫描，实时绘图并保存 CSV。
"""
from ivlab.core.config import ScanConfig
from ivlab.scanner.iv_scanner import IVScanner


NAME = "基础 IV 扫描"
DESCRIPTION = "Keithley 2400 电压源 IV 扫描（单向/双向/往返）"
ICON = "📈"

INSTRUMENTS = {
    "k2400": {"type": "keithley2400", "required": True},
}

PARAMS = [
    {"name": "start_v", "label": "起始电压 (V)", "type": "float",
     "default": 0.0, "min": -200.0, "max": 200.0},
    {"name": "stop_v", "label": "终止电压 (V)", "type": "float",
     "default": 2.0, "min": -200.0, "max": 200.0},
    {"name": "points", "label": "扫描点数", "type": "int",
     "default": 51, "min": 2, "max": 10001},
    {"name": "nplc", "label": "NPLC", "type": "float",
     "default": 1.0, "min": 0.01, "max": 10.0},
    {"name": "compliance_i", "label": "电流限值 (A)", "type": "float",
     "default": 0.1, "min": 1e-9, "max": 10.0},
    {"name": "scan_type", "label": "扫描类型", "type": "choice",
     "choices": ["single", "double", "sweep"], "default": "single"},
    {"name": "n_average", "label": "平均次数", "type": "int",
     "default": 1, "min": 1, "max": 100},
    {"name": "external_trigger", "label": "使用外部触发", "type": "bool",
     "default": False},
    {"name": "trigger_timeout", "label": "外部触发超时 (s)", "type": "float",
     "default": 30.0, "min": 0.1, "max": 3600.0},
    {"name": "output_trigger", "label": "输出触发同步其他设备", "type": "bool",
     "default": False},
    {"name": "trigger_output_event", "label": "触发输出时机", "type": "choice",
     "choices": ["SENS", "SOUR", "DEL"], "default": "SENS"},
]


def run(instruments, params, context):
    """执行基础 IV 扫描。"""
    k2400 = instruments["k2400"]

    context.log(
        f"配置 IV 扫描: {params['start_v']}V -> {params['stop_v']}V, "
        f"{params['points']} 点, {params['scan_type']}"
    )

    config = ScanConfig(
        start_v=params["start_v"],
        stop_v=params["stop_v"],
        points=params["points"],
        nplc=params["nplc"],
        compliance_i=params["compliance_i"],
        source_mode="voltage",
        source_delay=0.0,
        output_on_before=True,
        output_off_after=True,
        n_average=params["n_average"],
        scan_type=params["scan_type"],
        external_trigger=params.get("external_trigger", False),
        external_trigger_timeout=params.get("trigger_timeout", 30.0),
        output_trigger=params.get("output_trigger", False),
        trigger_output=params.get("trigger_output_event", "SENS"),
    )

    scanner = IVScanner(k2400, config)
    results = scanner.run()

    if not results:
        context.error("扫描未返回数据")
        context.done(success=False)
        return

    result = results[0]
    context.log(
        f"扫描完成，电压范围: {result.voltages[0]:.3f}V ~ {result.voltages[-1]:.3f}V, "
        f"电流范围: {result.currents.min():.3e}A ~ {result.currents.max():.3e}A"
    )

    for v, i in zip(result.voltages, result.currents):
        context.point(voltage=v, current=i)

    context.done(success=True)
