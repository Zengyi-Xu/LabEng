"""Cornerstone 260 波长扫描例程。

移动单色仪到一系列波长位置，记录实际波长、快门/光栅状态。
可扩展接入光功率计做光谱扫描。
"""
from ivlab.scanner.wavelength_scanner import WavelengthScanConfig, WavelengthScanner


NAME = "波长扫描"
DESCRIPTION = "Cornerstone 260 单色仪波长扫描"
ICON = "🌊"

INSTRUMENTS = {
    "cs260": {"type": "cornerstone260", "required": True},
}

PARAMS = [
    {"name": "start_nm", "label": "起始波长 (nm)", "type": "float",
     "default": 400.0, "min": 200.0, "max": 2000.0},
    {"name": "stop_nm", "label": "终止波长 (nm)", "type": "float",
     "default": 410.0, "min": 200.0, "max": 2000.0},
    {"name": "step_nm", "label": "步长 (nm)", "type": "float",
     "default": 2.0, "min": 0.01, "max": 100.0},
    {"name": "dwell_s", "label": "到位后驻留时间 (s)", "type": "float",
     "default": 0.0, "min": 0.0, "max": 10.0},
    {"name": "scan_type", "label": "扫描类型", "type": "choice",
     "choices": ["single", "double"], "default": "single"},
    {"name": "close_shutter_after", "label": "扫描结束后关闭快门", "type": "bool",
     "default": False},
]


def _progress_wrapper(context):
    """把 WavelengthScanner 的进度回调转成例程进度。"""
    def callback(current: int, total: int, wl: float, power):
        context.progress(current, total)
        context.log(f"波长 {wl:.2f} nm" + (f", 功率 {power:.3e}" if power is not None else ""))
    return callback


def run(instruments, params, context):
    """执行波长扫描。"""
    cs260 = instruments["cs260"]

    config = WavelengthScanConfig(
        start_nm=params["start_nm"],
        stop_nm=params["stop_nm"],
        step_nm=params["step_nm"],
        dwell_s=params["dwell_s"],
        scan_type=params["scan_type"],
        close_shutter_after=params["close_shutter_after"],
    )

    scanner = WavelengthScanner(cs260, config)
    context.log(
        f"开始波长扫描: {params['start_nm']} -> {params['stop_nm']} nm, "
        f"步长 {params['step_nm']} nm"
    )

    results = scanner.run(progress_callback=_progress_wrapper(context))

    for r in results:
        direction = r.direction
        for actual_wl in r.actual:
            context.point(wavelength=actual_wl, direction=direction)

    context.log(f"扫描完成，共 {len(results)} 个方向")
    context.done(success=True)
