"""回滞扫描与分析例程。

Keithley 2400 执行双向扫描，计算回滞面积、回滞指数、最大 ΔI、对称因子。
"""
from ivlab.core.config import ScanConfig
from ivlab.scanner.hysteresis import HysteresisAnalyzer
from ivlab.scanner.iv_scanner import IVScanner


NAME = "回滞扫描分析"
DESCRIPTION = "Keithley 2400 双向 IV 扫描 + 回滞分析"
ICON = "🔄"

INSTRUMENTS = {
    "k2400": {"type": "keithley2400", "required": True},
}

PARAMS = [
    {"name": "start_v", "label": "起始电压 (V)", "type": "float",
     "default": -1.0, "min": -200.0, "max": 200.0},
    {"name": "stop_v", "label": "终止电压 (V)", "type": "float",
     "default": 1.0, "min": -200.0, "max": 200.0},
    {"name": "points", "label": "扫描点数", "type": "int",
     "default": 101, "min": 2, "max": 10001},
    {"name": "nplc", "label": "NPLC", "type": "float",
     "default": 1.0, "min": 0.01, "max": 10.0},
    {"name": "compliance_i", "label": "电流限值 (A)", "type": "float",
     "default": 0.1, "min": 1e-9, "max": 10.0},
    {"name": "n_average", "label": "平均次数", "type": "int",
     "default": 2, "min": 1, "max": 100},
    {"name": "randomize_direction", "label": "随机化扫描方向", "type": "bool",
     "default": False},
]


def run(instruments, params, context):
    """执行回滞扫描与分析。"""
    k2400 = instruments["k2400"]

    context.log(
        f"配置回滞扫描: {params['start_v']}V -> {params['stop_v']}V, "
        f"{params['points']} 点, 平均 {params['n_average']} 次"
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
        randomize_direction=params["randomize_direction"],
        scan_type="double",
    )

    scanner = IVScanner(k2400, config)
    results = scanner.run()

    if not results:
        context.error("扫描未返回数据")
        context.done(success=False)
        return

    fwd_results = [r for r in results if r.direction == "forward"]
    bwd_results = [r for r in results if r.direction == "backward"]

    if not fwd_results or not bwd_results:
        context.error("未找到配对的双向扫描结果")
        context.done(success=False)
        return

    fwd = fwd_results[-1]
    bwd = bwd_results[-1]

    analyzer = HysteresisAnalyzer()
    h_result = analyzer.analyze(fwd, bwd)

    context.log("=== 回滞分析结果 ===")
    context.log(f"回滞面积: {h_result.hysteresis_area:.3e} V·A")
    context.log(f"回滞指数: {h_result.hysteresis_index:.4f}")
    context.log(f"最大 ΔI:   {h_result.delta_i_max:.3e} A")
    context.log(f"对称因子: {h_result.symmetry_factor:.3f}")

    # 绘图：把正向和反向数据合并为一条连续曲线
    for v, i in zip(fwd.voltages, fwd.currents):
        context.point(voltage=v, current=i, direction="forward")
    for v, i in zip(bwd.voltages, bwd.currents):
        context.point(voltage=v, current=i, direction="backward")

    context.done(success=True)
