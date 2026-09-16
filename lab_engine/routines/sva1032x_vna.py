"""Siglent SVA1032X VNA 模式例程。

测量 S 参数（S11/S21），设置 Marker 并读取峰值与 Delta 读数。
"""
NAME = "SVA1032X VNA 测量"
DESCRIPTION = "Siglent SVA1032X 矢量网络分析（S11/S21）"
ICON = "📡"

INSTRUMENTS = {
    "sva": {"type": "sva1032x", "required": True},
}

PARAMS = [
    {"name": "param", "label": "测量参数", "type": "choice",
     "choices": ["S11", "S21"], "default": "S21"},
    {"name": "start_hz", "label": "起始频率 (Hz)", "type": "float",
     "default": 1e6, "min": 0.0, "max": 1e12},
    {"name": "stop_hz", "label": "终止频率 (Hz)", "type": "float",
     "default": 3.2e9, "min": 0.0, "max": 1e12},
    {"name": "points", "label": "扫描点数", "type": "int",
     "default": 1601, "min": 2, "max": 10001},
    {"name": "ref_level", "label": "参考电平 (dB)", "type": "float",
     "default": 0.0, "min": -200.0, "max": 200.0},
    {"name": "scale", "label": "Scale/Div (dB)", "type": "float",
     "default": 10.0, "min": 0.01, "max": 100.0},
    {"name": "ref_pos", "label": "参考点位置 (0~10)", "type": "int",
     "default": 5, "min": 0, "max": 10},
    {"name": "marker_freq_hz", "label": "Marker2 频率 (Hz)", "type": "float",
     "default": 2.4e9, "min": 0.0, "max": 1e12},
]


def run(instruments, params, context):
    """执行 VNA 测量。"""
    sva = instruments["sva"]

    context.log("设置 VNA 模式")
    sva.set_mode("vna")
    sva.set_trace_count(1)
    sva.set_vna_parameter(params["param"], trace=1)
    sva.set_vna_format("mlog", trace=1)

    sva.set_frequency(start=params["start_hz"], stop=params["stop_hz"])
    sva.set_sweep_points(params["points"])
    context.log(
        f"扫频: {params['start_hz'] / 1e6:g} MHz ~ {params['stop_hz'] / 1e6:g} MHz, "
        f"{params['points']} 点"
    )

    sva.set_amplitude(ref_level=params["ref_level"], scale_per_div=params["scale"])
    sva.set_reference_position(params["ref_pos"])

    context.log("执行单次扫描")
    sva.single_sweep()

    sva.set_marker(1, True)
    sva.set_marker_mode(1, "normal")
    sva.set_marker_peak(1)
    m1 = sva.get_marker(1)
    context.log(f"Marker1 (峰值): {m1['x'] / 1e6:.4f} MHz, {m1['y']:.3f} dB")

    sva.set_marker(2, True)
    sva.set_marker_mode(2, "delta")
    sva.set_marker_position(2, params["marker_freq_hz"])
    sva.set_marker_reference(2, 1)
    m2 = sva.get_marker(2)
    context.log(
        f"Marker2 (Delta): Δf = {m2['x'] / 1e3:g} kHz, Δ幅度 = {m2['y']:.3f} dB"
    )

    context.point(
        marker1_freq_hz=m1["x"],
        marker1_value_db=m1["y"],
        marker2_delta_freq_hz=m2["x"],
        marker2_delta_value_db=m2["y"],
    )

    errors = sva.check_errors()
    if errors:
        context.log(f"仪器错误队列: {errors}", level="warn")

    context.done(success=True)
