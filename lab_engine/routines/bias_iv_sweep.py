"""示例测试例程：GPD 偏置 + K2400 IV 扫描。

此例程演示如何通过引擎的插件接口，用 GPD 给被测件提供直流偏置电压，
再用 Keithley 2400 做小信号电压源 IV 扫描。
"""
from ivlab.core.config import ScanConfig
from ivlab.scanner.iv_scanner import IVScanner


NAME = "偏置 IV 扫描"
DESCRIPTION = "GPD CH1 提供 DUT 直流偏置，K2400 作为电压源执行单/双/回滞 IV 扫描"
ICON = "⚡"

INSTRUMENTS = {
    "k2400": {"type": "keithley2400", "required": True},
    "gpd": {"type": "gpd4303s", "required": True},
}

PARAMS = [
    {"name": "bias_v", "label": "GPD CH1 偏置电压 (V)", "type": "float",
     "default": 3.3, "min": 0.0, "max": 32.0},
    {"name": "bias_i_limit", "label": "GPD CH1 电流限制 (A)", "type": "float",
     "default": 0.5, "min": 0.0, "max": 3.0},
    {"name": "start_v", "label": "扫描起始电压 (V)", "type": "float",
     "default": -1.0, "min": -200.0, "max": 200.0},
    {"name": "stop_v", "label": "扫描终止电压 (V)", "type": "float",
     "default": 1.0, "min": -200.0, "max": 200.0},
    {"name": "points", "label": "扫描点数", "type": "int",
     "default": 51, "min": 2, "max": 10001},
    {"name": "scan_type", "label": "扫描类型", "type": "choice",
     "choices": ["single", "double", "sweep"], "default": "single"},
    {"name": "n_average", "label": "平均次数", "type": "int",
     "default": 1, "min": 1, "max": 100},
    {"name": "nplc", "label": "K2400 NPLC", "type": "float",
     "default": 1.0, "min": 0.01, "max": 10.0},
    {"name": "compliance_i", "label": "K2400 电流限值 (A)", "type": "float",
     "default": 0.1, "min": 1e-9, "max": 10.0},
    {"name": "source_delay", "label": "源建立延迟 (s)", "type": "float",
     "default": 0.0, "min": 0.0, "max": 10.0},
]


def run(instruments, params, context):
    """执行偏置 IV 扫描。

    Args:
        instruments: {"k2400": Keithley2400, "gpd": GPD4303S}
        params: 用户在 GUI 中输入的参数字典
        context: 引擎提供的 RoutineContext
    """
    k2400 = instruments["k2400"]
    gpd = instruments["gpd"]

    context.log(f"配置 GPD CH1: {params['bias_v']} V / {params['bias_i_limit']} A")
    gpd.set_voltage(1, params["bias_v"])
    gpd.set_current(1, params["bias_i_limit"])
    gpd.output_on()
    context.log("GPD 输出已打开")

    context.log("配置 K2400 电压源 IV 扫描...")
    config = ScanConfig(
        start_v=params["start_v"],
        stop_v=params["stop_v"],
        points=params["points"],
        nplc=params["nplc"],
        compliance_i=params["compliance_i"],
        source_mode="voltage",
        source_delay=params["source_delay"],
        output_on_before=True,
        output_off_after=True,
        n_average=params["n_average"],
        scan_type=params["scan_type"],
    )

    scanner = IVScanner(k2400, config)

    def progress_callback(avg_idx, total, result):
        context.progress(avg_idx, total)
        if context.is_stopped():
            scanner.stop()
            return
        for v, i, r, t in zip(
            result.voltages, result.currents, result.resistances, result.timestamps
        ):
            context.point(
                voltage=float(v),
                current=float(i),
                resistance=float(r),
                timestamp=float(t),
                direction=result.direction,
            )
            if context.is_stopped():
                scanner.stop()
                return

    results = scanner.run(progress_callback=progress_callback)

    avg = scanner.get_averaged_result()
    if avg is not None:
        context.data(
            voltages=avg.voltages.tolist(),
            currents=avg.currents.tolist(),
            resistances=avg.resistances.tolist(),
        )

    context.done(success=len(results) > 0)
