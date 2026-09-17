"""GPD-4303S 四通道直流电源参数设置例程。

不扫参，只按用户在 GUI 填写的参数设置指定通道的电压、电流，并控制输出开关。
"""

NAME = "GPD 设置电压电流"
DESCRIPTION = "设置 GPD-4303S 指定通道的电压、电流并控制输出"
ICON = "🔌"

INSTRUMENTS = {
    "gpd": {"type": "gpd4303s", "required": True},
}

PARAMS = [
    {"name": "channel", "label": "通道", "type": "choice",
     "choices": ["1", "2", "3", "4"], "default": "1"},
    {"name": "voltage", "label": "电压 (V)", "type": "float",
     "default": 5.0, "min": 0.0, "max": 32.0},
    {"name": "current", "label": "电流限制 (A)", "type": "float",
     "default": 1.0, "min": 0.0, "max": 3.0},
    {"name": "output_on", "label": "打开输出", "type": "bool", "default": True},
    {"name": "measure", "label": "设置后回读", "type": "bool", "default": True},
]


def run(instruments, params, context):
    """设置 GPD 指定通道的电压电流。"""
    gpd = instruments["gpd"]

    channel = int(params["channel"])
    voltage = float(params["voltage"])
    current = float(params["current"])

    context.log(f"设置 GPD CH{channel}: {voltage} V / {current} A")

    gpd.set_voltage(channel, voltage)
    gpd.set_current(channel, current)

    if params["output_on"]:
        gpd.output_on()
        context.log(f"CH{channel} 输出已打开")
    else:
        gpd.output_off()
        context.log(f"CH{channel} 输出已关闭")

    if params["measure"]:
        data = gpd.measure_all()
        actual_v = data["voltage"].get(channel)
        actual_i = data["current"].get(channel)
        context.log(f"回读 CH{channel}: V={actual_v} V, I={actual_i} A")
        context.point(voltage=actual_v, current=actual_i)

    context.log("设置完成")
    context.done(success=True)
