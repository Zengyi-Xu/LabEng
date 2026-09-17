"""CAP 低代码节点库。

直接复用 CAP_NN 中已经调通的主流程（main_cap.run_singleband / run_multiband），
把每次运行的输出重定向到 ctx.run_dir，便于 LabEng 统一管理数据。
"""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from . import config_cap as cfg
from .main_cap import run_singleband, run_multiband


@dataclass
class PortDef:
    name: str
    label: str
    data_type: str = "any"
    required: bool = True


@dataclass
class ParamDef:
    name: str
    label: str
    type: str = "str"
    default: Any = ""
    choices: List[str] = field(default_factory=list)
    minimum: Optional[float] = None
    maximum: Optional[float] = None


@dataclass
class NodeDef:
    type_id: str
    label: str
    category: str
    description: str
    inputs: List[PortDef]
    outputs: List[PortDef]
    params: List[ParamDef]
    func: Optional[Callable[[Dict[str, Any], Dict[str, Any], Any], Dict[str, Any]]]


CATEGORY_COLORS = {
    "数据源": "#3B82F6",
    "调制": "#06B6D4",
    "发射": "#10B981",
    "信道": "#F59E0B",
    "接收": "#8B5CF6",
    "均衡": "#DB2777",
    "解调": "#0891B2",
    "分析": "#EA580C",
    "画图": "#65A30D",
    "变量存取": "#475569",
}

NODES: Dict[str, NodeDef] = {}


def register(node_def: NodeDef) -> NodeDef:
    NODES[node_def.type_id] = node_def
    return node_def


def get_node_def(type_id: str) -> Optional[NodeDef]:
    return NODES.get(type_id)


def node_types_by_category() -> Dict[str, List[NodeDef]]:
    out: Dict[str, List[NodeDef]] = {}
    for nd in NODES.values():
        out.setdefault(nd.category, []).append(nd)
    return out


def _out_path(ctx, filename: str) -> Path:
    p = Path(filename)
    if p.is_absolute():
        return p
    return Path(ctx.run_dir) / p


def _redirect_dirs(run_dir: Path) -> None:
    """把 CAP 的输出目录指到本次运行目录，避免写包内 data。"""
    base = Path(run_dir)
    cfg.TXDATA_DIR = base / "txdata"
    cfg.RXDATA_DIR = base / "rxdata"
    cfg.NN_DIR = base / "nn"
    cfg.PLOT_DIR = base / "plots"
    cfg.RECORD_DIR = base / "records"
    cfg.GRID_SCAN_DIR = base / "grid_scans"
    for d in (cfg.TXDATA_DIR, cfg.RXDATA_DIR, cfg.NN_DIR, cfg.PLOT_DIR,
              cfg.RECORD_DIR, cfg.GRID_SCAN_DIR):
        Path(d).mkdir(parents=True, exist_ok=True)


def _save_record(ctx, name: str, record: dict) -> Path:
    out = Path(ctx.run_dir) / name

    def _default(obj):
        if isinstance(obj, np.ndarray):
            if np.iscomplexobj(obj):
                return {"real": obj.real.tolist(), "imag": obj.imag.tolist()}
            return obj.tolist()
        if isinstance(obj, (np.integer, np.floating)):
            return float(obj)
        if isinstance(obj, np.complexfloating):
            return {"real": float(obj.real), "imag": float(obj.imag)}
        return float(obj)

    with open(out, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2, default=_default)
    return out


def _fn_cap_singleband(inputs, params, ctx):
    """单带 CAP 离线收发仿真（等效 CAP_NN main_cap.run_singleband）。"""
    _redirect_dirs(ctx.run_dir)
    cfg.USE_VIRTUAL_CHANNEL = 1 if params.get("use_virtual_channel", True) else 0
    record = run_singleband(
        numofsymbols=int(params.get("numofsymbols", cfg.SB_NUMOFSYMBOLS)),
        order=int(params.get("order", cfg.SB_QAMORDER)),
        constellation=params.get("constellation", cfg.SB_CONSTELLATION),
        snr_db=float(params.get("snr_db", cfg.SB_SNR_DB)),
        seed=int(params.get("seed", 100)),
    )
    path = _save_record(ctx, "cap_singleband_record.json", record)
    # 保存发送端星座图
    qam_data = record["qam_data"]
    tx_signal = record["tx_signal"]
    plot_path = _out_path(ctx, "cap_tx_constellation.png")
    _plot_constellation(qam_data, "CAP TX Constellation", plot_path)
    ctx.log(f"单带 CAP 完成: BER={record['ber']:.3e}, SER={record['ser']:.3e}")
    ctx.log(f"结果 -> {path}")
    return {
        "record": record,
        "ser": record["ser"],
        "ber": record["ber"],
        "tx_signal": tx_signal,
        "qam_data": qam_data,
        "plot": str(plot_path),
    }


def _fn_cap_multiband(inputs, params, ctx):
    """多带 CAP 离线收发仿真（可选 LMS / NN 后均衡）。"""
    _redirect_dirs(ctx.run_dir)
    cfg.USE_VIRTUAL_CHANNEL = 1 if params.get("use_virtual_channel", True) else 0
    record = run_multiband(
        numofsymbols=int(params.get("numofsymbols", cfg.MB_NUMOFSYMBOLS)),
        order=int(params.get("order", cfg.MB_M)),
        constellation=params.get("constellation", cfg.MB_CONSTELLATION),
        snr_db=float(params.get("snr_db", cfg.MB_SNR_DB)),
        seed=int(params.get("seed", 1)),
        use_lms=bool(params.get("use_lms", True)),
        use_nn=bool(params.get("use_nn", False)),
    )
    path = _save_record(ctx, "cap_multiband_record.json", record)
    ctx.log(f"多带 CAP 完成: 平均原始 BER={record['raw_ber_avg']:.3e} -> {path}")
    return {"record": record, "raw_ber_avg": record["raw_ber_avg"]}


def _plot_constellation(symbols: np.ndarray, title: str, out: Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    sym = np.asarray(symbols).ravel()
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.scatter(np.real(sym), np.imag(sym), s=8, alpha=0.5)
    ax.set_title(title)
    ax.set_xlabel("I")
    ax.set_ylabel("Q")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def _fn_plot_constellation(inputs, params, ctx):
    symbols = np.asarray(inputs["symbols"]).ravel()
    title = str(params.get("title", "CAP Constellation"))
    out = Path(ctx.run_dir) / "cap_constellation.png"
    _plot_constellation(symbols, title, out)
    ctx.log(f"星座图已保存 -> {out}")
    return {"path": str(out)}


register(NodeDef(
    type_id="cap_singleband_sim",
    label="单带 CAP 仿真",
    category="分析",
    description="运行单带 CAP 收发链路（调制→成形→虚拟信道→Volterra+LMS→解调）",
    inputs=[],
    outputs=[
        PortDef("record", "运行记录"),
        PortDef("ser", "SER"),
        PortDef("ber", "BER"),
        PortDef("tx_signal", "TX 信号"),
        PortDef("qam_data", "发送符号", "complex"),
        PortDef("plot", "星座图路径"),
    ],
    params=[
        ParamDef("numofsymbols", "符号数", "int", cfg.SB_NUMOFSYMBOLS, minimum=100),
        ParamDef("order", "调制阶数", "int", cfg.SB_QAMORDER, minimum=2),
        ParamDef("constellation", "星座", "choice", cfg.SB_CONSTELLATION,
                 choices=["APSK", "QAM"]),
        ParamDef("snr_db", "信噪比 (dB)", "float", cfg.SB_SNR_DB),
        ParamDef("seed", "随机种子", "int", 100),
        ParamDef("use_virtual_channel", "使用虚拟信道", "bool", True),
    ],
    func=_fn_cap_singleband,
))

register(NodeDef(
    type_id="cap_multiband_sim",
    label="多带 CAP 仿真",
    category="分析",
    description="运行多带 CAP 收发链路（可选每子带 LMS 与 NN 后均衡）",
    inputs=[],
    outputs=[PortDef("record", "运行记录"), PortDef("raw_ber_avg", "平均原始 BER")],
    params=[
        ParamDef("numofsymbols", "符号数", "int", cfg.MB_NUMOFSYMBOLS, minimum=100),
        ParamDef("order", "调制阶数", "int", cfg.MB_M, minimum=2),
        ParamDef("constellation", "星座", "choice", cfg.MB_CONSTELLATION,
                 choices=["APSK", "QAM"]),
        ParamDef("snr_db", "信噪比 (dB)", "float", cfg.MB_SNR_DB),
        ParamDef("seed", "随机种子", "int", 1),
        ParamDef("use_virtual_channel", "使用虚拟信道", "bool", True),
        ParamDef("use_lms", "每子带 LMS 均衡", "bool", True),
        ParamDef("use_nn", "NN 后均衡（需脚本）", "bool", False),
    ],
    func=_fn_cap_multiband,
))

register(NodeDef(
    type_id="cap_plot_constellation",
    label="画星座图",
    category="画图",
    description="把复数符号流画成星座图并保存 PNG",
    inputs=[PortDef("symbols", "符号流", "complex")],
    outputs=[PortDef("path", "图片路径")],
    params=[ParamDef("title", "标题", "str", "CAP Constellation")],
    func=_fn_plot_constellation,
))
