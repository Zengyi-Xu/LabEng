"""DMT 主流程例程。

运行完整的 DMT 通信流程：QPSK 信道探测 → bitloading 传输 → 解调。
"""
import sys
from pathlib import Path

import numpy as np

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


NAME = "DMT 完整流程"
DESCRIPTION = "QPSK 信道探测 → bitloading 传输 → 解调"
ICON = "📡"

INSTRUMENTS = {
    "awg": {"type": "m8190a", "required": False},
    "scope": {"type": "oscilloscope", "required": False},
}

PARAMS = [
    {"name": "offline", "label": "离线模式", "type": "bool", "default": True},
    {"name": "use_awg", "label": "使用 AWG 下载波形", "type": "bool", "default": False},
    {"name": "use_virtual_channel", "label": "使用虚拟信道", "type": "bool", "default": False},
    {"name": "use_nn", "label": "使用 NN 后均衡", "type": "bool", "default": False},
    {"name": "pre_equ_flag", "label": "预均衡模式", "type": "int",
     "default": 3, "min": 0, "max": 4},
    {"name": "pilot_pattern", "label": "导频图案", "type": "choice",
     "choices": ["training_only", "comb", "mesh"], "default": "training_only"},
]


def run(instruments, params, context):
    """执行 DMT 完整流程。"""
    if not HAS_DMT:
        context.error(f"DMT_PY_NN 导入失败: {_import_error}")
        context.done(success=False)
        return

    # 配置全局参数
    dmt_config.OFFLINE_FLAG = 1 if params["offline"] else 0
    dmt_config.USE_VIRTUAL_CHANNEL = 1 if params["use_virtual_channel"] else 0
    dmt_config.PRE_EQU_FLAG = params["pre_equ_flag"]
    dmt_config.PILOT_PATTERN = params["pilot_pattern"]
    dmt_config.PLOT_SHOW = False

    run_id = context.run_id
    context.log(f"开始 DMT 流程 (run_id={run_id})")

    try:
        # STEP1: QPSK TX
        context.log("STEP1: 生成 QPSK 探测波形")
        tx_qpsk = step1_generate_qpsk_tx(
            use_awg=params["use_awg"],
            run_id=run_id,
        )
        context.point(stage="step1", waveform_len=len(tx_qpsk["tx_waveform"]))

        # STEP2: QPSK RX & SNR
        context.log("STEP2: 接收 QPSK 并估计 SNR")
        snrs, rx_sync = step2_receive_qpsk(
            tx_qpsk,
            offline=params["offline"],
            use_virtual_channel=params["use_virtual_channel"],
            run_id=run_id,
        )
        mean_snr = np.nanmean(snrs)
        context.point(stage="step2", mean_snr=mean_snr, mean_snr_db=10 * np.log10(mean_snr))

        # STEP3: Bitloading TX
        context.log("STEP3: 生成 bitloading 波形")
        tx_bpl = step3_generate_bitloading_tx(
            snrs,
            use_awg=params["use_awg"],
            run_id=run_id,
        )
        context.point(
            stage="step3",
            waveform_len=len(tx_bpl["tx_waveform"]),
            datarate_gbps=tx_bpl.get("datarate_gbps", 0.0),
        )

        # STEP4: Bitloading RX
        context.log("STEP4: 接收 bitloading 并解调")
        res = step4_receive_bitloading(
            tx_bpl,
            offline=params["offline"],
            use_nn=params["use_nn"],
            use_virtual_channel=params["use_virtual_channel"],
            run_id=run_id,
        )
        context.point(
            stage="step4",
            ber=res.get("ber", np.nan),
            ser=res.get("ser", np.nan),
        )

        context.log(f"DMT 流程完成: BER={res.get('ber', np.nan):.3e}, SER={res.get('ser', np.nan):.3e}")
        context.data(result=res)
        context.done(success=True)

    except Exception as exc:
        context.error(f"DMT 流程异常: {exc}")
        context.done(success=False)
