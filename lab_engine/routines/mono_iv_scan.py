"""单色仪 + 源表联动扫描例程。

Cornerstone 260 改变波长，Keithley 2400 固定电压源输出并读取电流，
得到波长-电压-电流-电阻数据。
"""
import time


NAME = "单色仪 IV 联动扫描"
DESCRIPTION = "CS260 扫波长，K2400 固定电压读电流"
ICON = "🌈"

INSTRUMENTS = {
    "cs260": {"type": "cornerstone260", "required": True},
    "k2400": {"type": "keithley2400", "required": True},
}

PARAMS = [
    {"name": "start_nm", "label": "起始波长 (nm)", "type": "float",
     "default": 400.0, "min": 200.0, "max": 2000.0},
    {"name": "stop_nm", "label": "终止波长 (nm)", "type": "float",
     "default": 410.0, "min": 200.0, "max": 2000.0},
    {"name": "steps", "label": "扫描步数", "type": "int",
     "default": 10, "min": 2, "max": 1000},
    {"name": "voltage", "label": "K2400 输出电压 (V)", "type": "float",
     "default": 1.0, "min": -200.0, "max": 200.0},
    {"name": "compliance_i", "label": "电流限值 (A)", "type": "float",
     "default": 0.1, "min": 1e-9, "max": 10.0},
    {"name": "settle_s", "label": "到位后等待时间 (s)", "type": "float",
     "default": 0.2, "min": 0.0, "max": 10.0},
]


def run(instruments, params, context):
    """执行单色仪 + 源表联动扫描。"""
    cs260 = instruments["cs260"]
    k2400 = instruments["k2400"]

    start = params["start_nm"]
    stop = params["stop_nm"]
    steps = params["steps"]
    voltage = params["voltage"]
    settle = params["settle_s"]

    wavelengths = [start + i * (stop - start) / (steps - 1) for i in range(steps)]

    context.log(f"配置 K2400 电压源: {voltage} V")
    k2400.set_source_mode("voltage")
    k2400.set_compliance(params["compliance_i"])
    k2400.set_output_level(voltage)
    k2400.output_on()

    context.log(f"开始波长扫描: {start} -> {stop} nm, 共 {steps} 步")

    try:
        for i, wl in enumerate(wavelengths, 1):
            if context.is_stopped():
                context.log("扫描被用户停止")
                break

            context.log(f"[{i}/{steps}] 移动单色仪到 {wl:.2f} nm")
            actual_wl = cs260.goto_wavelength(wl)
            if settle > 0:
                time.sleep(settle)

            reading = k2400.measure()
            context.point(
                step=i,
                target_wavelength=wl,
                wavelength=actual_wl,
                voltage=reading["voltage"],
                current=reading["current"],
                resistance=reading["resistance"],
            )
            context.progress(i, steps)

        context.log("扫描完成")
    finally:
        k2400.output_off()
        context.log("K2400 输出已关闭")

    context.done(success=True)
