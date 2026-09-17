"""DMT 低代码发射与画图示例。

演示如何把 lab_engine.commlib 里的 DMT 代码节点串成一条 LabEng 测试例程，
运行结果（时域图、频谱图、波形 txt）保存到 context.output_dir。
"""
from types import SimpleNamespace

import numpy as np

NAME = "DMT 低代码发射与画图"
DESCRIPTION = "用代码节点离线生成 DMT 波形，并保存时域/频域图"
ICON = "📡"
INSTRUMENTS = {}
PARAMS = [
    {"name": "datano", "label": "每载波符号数", "type": "int", "default": 100, "min": 10, "max": 10000},
    {"name": "constellation", "label": "星座", "type": "choice",
     "choices": ["QAM", "APSK"], "default": "QAM"},
]


def _make_graph(datano: int, constellation: str):
    return {
        "nodes": [
            {"id": "src", "type": "dmt.bit_source",
             "params": {"datano": datano, "seed": 1}},
            {"id": "tx", "type": "dmt.dmt_tx_full",
             "params": {"constellation": constellation, "datano": datano}},
            {"id": "plot_t", "type": "dmt.plot_time",
             "params": {"title": "DMT TX Time", "filename": "dmt_tx_time"}},
            {"id": "plot_f", "type": "dmt.plot_spectrum",
             "params": {"title": "DMT TX Spectrum", "filename": "dmt_tx_spectrum"}},
            {"id": "save", "type": "dmt.save_var",
             "params": {"filename": "dmt_tx_waveform.txt"}},
        ],
        "edges": [
            {"source": "src", "source_port": "RQ", "target": "tx", "target_port": "RQ"},
            {"source": "tx", "source_port": "waveform", "target": "plot_t", "target_port": "waveform"},
            {"source": "tx", "source_port": "waveform", "target": "plot_f", "target_port": "waveform"},
            {"source": "tx", "source_port": "waveform", "target": "save", "target_port": "value"},
        ],
    }


def run(instruments, params, context):
    from lab_engine.commlib.executor import run_graph

    graph = _make_graph(int(params["datano"]), params["constellation"])
    ctx = SimpleNamespace(
        run_dir=str(context.output_dir),
        log=lambda msg, *args, **kwargs: context.log(str(msg)),
    )
    context.log("开始 DMT 低代码发射链路")
    outs = run_graph(graph, ctx)
    waveform = outs["tx"]["waveform"]
    context.log(f"波形长度: {len(waveform)}")
    context.data(waveform_length=len(waveform), output_dir=str(context.output_dir))
    context.done(success=True)
