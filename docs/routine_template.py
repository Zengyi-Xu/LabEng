"""例程模板。

复制本文件到 lab_engine/routines/ 目录，改个文件名，然后修改：
- NAME：GUI 下拉框里显示的名字（必须唯一）
- DESCRIPTION：简短描述
- ICON：可选，显示在 GUI 里
- INSTRUMENTS：本例程要用到的仪器别名和类型
- PARAMS：运行页需要用户填写的参数
- run()：具体的测试逻辑

注意：
- 不要在文件里写 if __name__ == "__main__": 测试代码。
- 长循环里必须检查 context.is_stopped()，响应用户点击「停止」。
- 用 context.log() 输出日志，context.point() 上报数据点，context.done() 结束例程。
"""

NAME = "我的例程"
DESCRIPTION = "在这里写一句简短描述"
ICON = "🔬"

INSTRUMENTS = {
    "k2400": {"type": "keithley2400", "required": True},
}

PARAMS = [
    {"name": "start_v", "label": "起始电压 (V)", "type": "float", "default": 0.0},
    {"name": "stop_v", "label": "终止电压 (V)", "type": "float", "default": 1.0},
    {"name": "points", "label": "点数", "type": "int", "default": 11},
]


def run(instruments, params, context):
    """例程入口，由引擎在后台线程调用。"""
    k2400 = instruments["k2400"]

    context.log(f"开始扫描，从 {params['start_v']} V 到 {params['stop_v']} V")

    import numpy as np
    voltages = np.linspace(params["start_v"], params["stop_v"], params["points"])

    for i, v in enumerate(voltages):
        # 用户点击「停止」时立即退出
        if context.is_stopped():
            context.log("用户停止", level="warning")
            break

        k2400.set_output_level(v)
        data = k2400.measure()

        # 上报数据点，运行页会实时绘图
        context.point(voltage=v, current=data["current"])

        # 更新进度条
        context.progress(i + 1, len(voltages))

    context.log("例程运行完成")
    context.done(success=True)
