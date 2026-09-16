"""NN 后均衡例程。

读取 TX/RX 波形文件，运行 ZY_BiGRU_GPU 神经网络均衡，输出均衡后波形。
"""
import sys
from pathlib import Path

import numpy as np

_DMT_PY_NN = Path(__file__).resolve().parents[4] / "DMT_PY_NN"
if _DMT_PY_NN.exists():
    sys.path.insert(0, str(_DMT_PY_NN))

try:
    import config as dmt_config
    from nn_equalizer import run_nn_equalizer
    from utils import load_txt
    HAS_DMT = True
except Exception as _exc:
    HAS_DMT = False
    _import_error = str(_exc)


NAME = "NN 后均衡"
DESCRIPTION = "运行 ZY_BiGRU_GPU 神经网络后均衡"
ICON = "🧠"

INSTRUMENTS = {}

PARAMS = [
    {"name": "tx_file", "label": "TX 波形文件", "type": "str",
     "default": str(dmt_config.NN_TX_FILE) if HAS_DMT else ""},
    {"name": "rx_file", "label": "RX 波形文件", "type": "str",
     "default": str(dmt_config.NN_RX1_FILE) if HAS_DMT else ""},
    {"name": "output_file", "label": "输出文件", "type": "str",
     "default": str(dmt_config.NN_OUTPUT1_FILE) if HAS_DMT else ""},
    {"name": "use_pretrained", "label": "使用预训练模型", "type": "bool", "default": True},
]


def run(instruments, params, context):
    """执行 NN 均衡。"""
    if not HAS_DMT:
        context.error(f"DMT_PY_NN 导入失败: {_import_error}")
        context.done(success=False)
        return

    tx_file = Path(params["tx_file"])
    rx_file = Path(params["rx_file"])

    if not tx_file.exists():
        context.error(f"TX 文件不存在: {tx_file}")
        context.done(success=False)
        return
    if not rx_file.exists():
        context.error(f"RX 文件不存在: {rx_file}")
        context.done(success=False)
        return

    context.log(f"读取 TX: {tx_file}")
    tx = load_txt(tx_file)
    context.log(f"读取 RX: {rx_file}")
    rx = load_txt(rx_file)

    context.log("运行 NN 均衡...")
    try:
        rx_eq = run_nn_equalizer(tx.ravel(), rx.ravel(), nn_dir=dmt_config.NN_DIR)
        context.log(f"NN 输出长度: {len(rx_eq)}")

        out_file = Path(params["output_file"])
        np.savetxt(out_file, rx_eq)
        context.log(f"结果已保存: {out_file}")

        context.point(
            tx_len=len(tx),
            rx_len=len(rx),
            rx_eq_len=len(rx_eq),
            output_file=str(out_file),
        )
        context.done(success=True)
    except Exception as exc:
        context.error(f"NN 均衡失败: {exc}")
        context.done(success=False)
