"""双 Keithley 2400 联合 IV 扫描例程。

第一台 K2400 执行 IV 扫描；可选的第二台 K2400 保持固定偏置。
"""
import numpy as np

NAME = "Duo_2400_IV"
DESCRIPTION = "双 Keithley 2400 联合 IV 扫描"
ICON = "🔬"

INSTRUMENTS = {
    "inst_1": {"type": "keithley2400", "required": True},
    "inst_2": {"type": "keithley2400", "required": False},
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
    {"name": "bias_v", "label": "第二台偏置电压 (V)", "type": "float",
     "default": 0.0, "min": -200.0, "max": 200.0},
]


def run(instruments, params, context):
    """执行双机联合 IV 扫描。"""
    k1 = instruments["inst_1"]
    k2 = instruments.get("inst_2")

    context.log(f"开始 Duo_2400_IV: {params['start_v']}V -> {params['stop_v']}V, "
                f"{params['points']} 点")

    # 配置第二台保持偏置（如已连接）
    if k2 is not None:
        context.log(f"inst_2 保持偏置 {params['bias_v']}V")
        k2.set_source_mode("voltage")
        k2.set_compliance(params["compliance_i"])
        k2.set_nplc(params["nplc"])
        k2.set_output_level(params["bias_v"])
        k2.output_on()

    try:
        # 配置第一台扫描
        k1.set_source_mode("voltage")
        k1.set_compliance(params["compliance_i"])
        k1.set_nplc(params["nplc"])
        k1.output_on()

        voltages = np.linspace(params["start_v"], params["stop_v"], params["points"])
        if params["scan_type"] == "double":
            voltages = np.concatenate([voltages, voltages[::-1]])
        elif params["scan_type"] == "sweep":
            voltages = np.concatenate([voltages, voltages[::-1][1:-1]])

        for i, v in enumerate(voltages):
            if context.is_stopped():
                context.log("用户停止", level="warning")
                break
            k1.set_output_level(v)
            data = k1.measure()
            context.point(voltage=v, current=data["current"])
            context.progress(i + 1, len(voltages))

        context.log("Duo_2400_IV 完成")
        context.done(success=True)

    except Exception as exc:
        context.error(f"扫描异常: {exc}")
        context.done(success=False)
    finally:
        try:
            k1.output_off()
        except Exception:
            pass
        if k2 is not None:
            try:
                k2.output_off()
            except Exception:
                pass
