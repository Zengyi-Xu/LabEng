NAME = "IV_2400 基础扫描"
DESCRIPTION = ""
ICON = "🔬"

INSTRUMENTS = {
    "inst_2": {'type': 'keithley2400', 'required': True}
}

PARAMS = []


def run(instruments, params, context):
    """执行例程。"""
    context.log("开始运行: 基础 IV 扫描")
    inst_2 = instruments.get("inst_2")

    # TODO: 在这里补充具体的测试逻辑
    # 例如：
    # for v in np.linspace(params.get("start_v", 0), params.get("stop_v", 1), params.get("points", 11)):
    #     k2400.set_output_level(v)
    #     data = k2400.measure()
    #     context.point(voltage=v, current=data["current"])

    context.log("例程运行完成")
    context.done(success=True)
