"""Keithley 2400 源表参数设置例程。

不扫参，只按用户在 GUI 填写的参数设置电压/电流，并控制输出开关。
"""

NAME = "2400 设置电压电流"
DESCRIPTION = "设置 Keithley 2400 输出电压、电流限值并控制输出"
ICON = "🔌"

INSTRUMENTS = {
    "k2400": {"type": "keithley2400", "required": True},
}

PARAMS = [
    {"name": "source_mode", "label": "源模式", "type": "choice",
     "choices": ["voltage", "current"], "default": "voltage"},
    {"name": "level", "label": "输出电平", "type": "float",
     "default": 1.0},
    {"name": "compliance", "label": "合规限值", "type": "float",
     "default": 0.1},
    {"name": "nplc", "label": "NPLC", "type": "float",
     "default": 1.0, "min": 0.01, "max": 10.0},
    {"name": "output_on", "label": "打开输出", "type": "bool", "default": True},
    {"name": "measure", "label": "设置后回读", "type": "bool", "default": True},
]


def run(instruments, params, context):
    """设置 Keithley 2400 输出参数。"""
    k2400 = instruments["k2400"]

    source_mode = params["source_mode"]
    level = float(params["level"])
    compliance = float(params["compliance"])
    nplc = float(params["nplc"])

    context.log(f"设置 2400 为 {source_mode} 源，电平 {level}")

    k2400.set_source_mode(source_mode)
    k2400.set_output_level(level)
    k2400.set_compliance(compliance)
    k2400.set_nplc(nplc)

    if params["output_on"]:
        k2400.output_on()
        context.log("输出已打开")
    else:
        k2400.output_off()
        context.log("输出已关闭")

    if params["measure"]:
        data = k2400.measure()
        context.log(
            f"回读: V={data['voltage']} V, I={data['current']} A, "
            f"R={data['resistance']} Ohm"
        )
        context.point(voltage=data["voltage"], current=data["current"])

    context.log("设置完成")
    context.done(success=True)
