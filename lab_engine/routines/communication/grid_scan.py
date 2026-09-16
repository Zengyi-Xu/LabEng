"""DMT 参数网格扫描例程。

对 Keithley 偏置（电压/电流）和 AWG Vpp 做二维扫描，每个点运行 DMT pipeline。
"""
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

# 导入 DMT_PY_NN（假设两个仓库在同一 workspace 下）
_DMT_PY_NN = Path(__file__).resolve().parents[4] / "DMT_PY_NN"
if _DMT_PY_NN.exists():
    sys.path.insert(0, str(_DMT_PY_NN))

try:
    import config as dmt_config
    from main import (
        step1_generate_qpsk_tx,
        step2_receive_qpsk,
        step3_generate_bitloading_tx,
        step4_receive_bitloading,
    )
    HAS_DMT = True
except Exception as _exc:
    HAS_DMT = False
    _import_error = str(_exc)


NAME = "DMT 网格扫描"
DESCRIPTION = "Keithley 偏置 × AWG Vpp 二维扫描，每个点运行 DMT pipeline"
ICON = "📊"

INSTRUMENTS = {
    "k2400": {"type": "keithley2400", "required": True},
    "awg": {"type": "m8190a", "required": False},
    "scope": {"type": "oscilloscope", "required": False},
}

PARAMS = [
    {"name": "param1_mode", "label": "参数1类型", "type": "choice",
     "choices": ["voltage", "current"], "default": "voltage"},
    {"name": "param1_start", "label": "参数1起始", "type": "float",
     "default": 0.0, "min": -200.0, "max": 200.0},
    {"name": "param1_stop", "label": "参数1终止", "type": "float",
     "default": 1.0, "min": -200.0, "max": 200.0},
    {"name": "param1_step", "label": "参数1步长", "type": "float",
     "default": 0.1, "min": 1e-6, "max": 200.0},
    {"name": "vpp_start", "label": "Vpp 起始 (V)", "type": "float",
     "default": 0.1, "min": 0.0, "max": 2.0},
    {"name": "vpp_stop", "label": "Vpp 终止 (V)", "type": "float",
     "default": 1.0, "min": 0.0, "max": 2.0},
    {"name": "vpp_step", "label": "Vpp 步长 (V)", "type": "float",
     "default": 0.1, "min": 0.01, "max": 2.0},
    {"name": "run_mode", "label": "运行模式", "type": "choice",
     "choices": ["step1-4", "step1-2"], "default": "step1-4"},
    {"name": "step4_repeats", "label": "Step4 重复次数", "type": "int",
     "default": 1, "min": 1, "max": 20},
    {"name": "offline", "label": "离线模式", "type": "bool", "default": True},
    {"name": "use_virtual_channel", "label": "虚拟信道", "type": "bool", "default": False},
    {"name": "use_nn", "label": "使用 NN 均衡", "type": "bool", "default": False},
    {"name": "keithley_compliance", "label": "K2400 限值", "type": "float",
     "default": 0.1, "min": 1e-9, "max": 10.0},
    {"name": "keithley_nplc", "label": "K2400 NPLC", "type": "float",
     "default": 1.0, "min": 0.01, "max": 10.0},
]


def _make_grid(start: float, stop: float, step: float) -> np.ndarray:
    n = int(np.round((stop - start) / step)) + 1
    vals = start + np.arange(n) * step
    if len(vals) > 0:
        vals[-1] = min(vals[-1], stop)
    return vals


def run(instruments, params, context):
    """执行 DMT 网格扫描。"""
    if not HAS_DMT:
        context.error(f"DMT_PY_NN 导入失败: {_import_error}")
        context.done(success=False)
        return

    k2400 = instruments["k2400"]

    # 配置 K2400
    context.log("配置 Keithley 2400...")
    k2400.set_source_mode(params["param1_mode"])
    k2400.set_compliance(params["keithley_compliance"])
    k2400.set_nplc(params["keithley_nplc"])
    k2400.set_range(auto=True)

    # 配置 DMT 全局参数
    dmt_config.OFFLINE_FLAG = 1 if params["offline"] else 0
    dmt_config.USE_VIRTUAL_CHANNEL = 1 if params["use_virtual_channel"] else 0
    dmt_config.PLOT_SHOW = False  # 不在例程中弹出 matplotlib 窗口

    bias_vals = _make_grid(params["param1_start"], params["param1_stop"], params["param1_step"])
    vpp_vals = _make_grid(params["vpp_start"], params["vpp_stop"], params["vpp_step"])
    total = len(bias_vals) * len(vpp_vals)

    context.log(f"网格扫描: {len(bias_vals)} × {len(vpp_vals)} = {total} 点")

    results: List[Dict[str, Any]] = []
    point_idx = 0

    for bias in bias_vals:
        for vpp in vpp_vals:
            if context.is_stopped():
                context.log("扫描被用户停止")
                break

            point_idx += 1
            context.progress(point_idx, total)
            context.log(f"[{point_idx}/{total}] bias={bias:.3f} {params['param1_mode']}, Vpp={vpp:.3f} V")

            # 设置偏置
            k2400.set_output_level(bias)
            k2400.output_on()

            # 修改 AWG Vpp（通过 config）
            old_vpp = dmt_config.AWG_VPP
            dmt_config.AWG_VPP = vpp

            try:
                # 运行 DMT pipeline
                run_id = f"grid_{point_idx:04d}"
                tx_qpsk = step1_generate_qpsk_tx(
                    use_awg=not params["offline"],
                    run_id=run_id,
                )
                snrs, _ = step2_receive_qpsk(
                    tx_qpsk,
                    offline=params["offline"],
                    use_virtual_channel=params["use_virtual_channel"],
                    run_id=run_id,
                )

                ber = ser = np.nan
                rate_gbps = np.nan
                if params["run_mode"] == "step1-4":
                    tx_bpl = step3_generate_bitloading_tx(
                        snrs,
                        use_awg=not params["offline"],
                        run_id=run_id,
                    )
                    res = step4_receive_bitloading(
                        tx_bpl,
                        offline=params["offline"],
                        use_nn=params["use_nn"],
                        use_virtual_channel=params["use_virtual_channel"],
                        run_id=run_id,
                    )
                    ber = res.get("ber", np.nan)
                    ser = res.get("ser", np.nan)
                    rate_gbps = tx_bpl.get("datarate_gbps", np.nan)

                snr_db = 10 * np.log10(np.nanmean(snrs)) if np.any(np.isfinite(snrs)) else np.nan
                row = {
                    "point_idx": point_idx,
                    "bias": bias,
                    "vpp": vpp,
                    "snr_db": snr_db,
                    "ber": ber,
                    "ser": ser,
                    "rate_gbps": rate_gbps,
                }
                results.append(row)
                context.point(**row)

            except Exception as exc:
                context.error(f"点 {point_idx} 失败: {exc}")
                results.append({
                    "point_idx": point_idx,
                    "bias": bias,
                    "vpp": vpp,
                    "snr_db": np.nan,
                    "ber": np.nan,
                    "ser": np.nan,
                    "rate_gbps": np.nan,
                    "error": str(exc),
                })
            finally:
                dmt_config.AWG_VPP = old_vpp

    k2400.output_off()
    context.log("网格扫描完成")
    context.data(results=results)
    context.done(success=True)
