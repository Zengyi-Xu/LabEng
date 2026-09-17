"""CAP 单带离线仿真（低代码节点示例）。

直接调用 lab_engine.commlib 里的 CAP 代码节点，在 context.output_dir
下生成误码率记录和发送端星座图。
"""
from types import SimpleNamespace

NAME = "CAP 单带离线仿真"
DESCRIPTION = "用代码节点运行单带 CAP 收发链路，保存 BER/SER 和星座图"
ICON = "📶"
INSTRUMENTS = {}
PARAMS = [
    {"name": "numofsymbols", "label": "符号数", "type": "int", "default": 500, "min": 100, "max": 50000},
    {"name": "order", "label": "调制阶数", "type": "int", "default": 16, "min": 2, "max": 1024},
    {"name": "constellation", "label": "星座", "type": "choice",
     "choices": ["APSK", "QAM"], "default": "QAM"},
    {"name": "snr_db", "label": "信噪比 (dB)", "type": "float", "default": 20.0},
    {"name": "seed", "label": "随机种子", "type": "int", "default": 1},
]


def run(instruments, params, context):
    from lab_engine.commlib.executor import run_graph

    graph = {
        "nodes": [
            {"id": "sim", "type": "cap.cap_singleband_sim", "params": {
                "numofsymbols": int(params["numofsymbols"]),
                "order": int(params["order"]),
                "constellation": params["constellation"],
                "snr_db": float(params["snr_db"]),
                "seed": int(params["seed"]),
                "use_virtual_channel": True,
            }},
        ],
        "edges": [],
    }
    ctx = SimpleNamespace(
        run_dir=str(context.output_dir),
        log=lambda msg, *args, **kwargs: context.log(str(msg)),
    )
    context.log("开始 CAP 单带离线仿真")
    outs = run_graph(graph, ctx)
    record = outs["sim"]["record"]
    context.log(f"CAP 完成: BER={record['ber']:.3e}, SER={record['ser']:.3e}")
    context.data(ber=record["ber"], ser=record["ser"])
    context.done(success=True)
