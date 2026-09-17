"""通用代码节点执行器。

输入是一张「节点连线图」的纯 dict 描述：
    {
      "nodes": [{"id": "n1", "type": "dmt.bit_source", "params": {...}}, ...],
      "edges": [{"source": "n1", "source_port": "dec",
                 "target": "n2", "target_port": "dec"}, ...]
    }
按拓扑顺序执行每个节点的 func(inputs, params, ctx)，并把输出按端口名传给下游。
"""
from typing import Any, Dict, List, Tuple

from lab_engine.commlib import registry


class FlowError(RuntimeError):
    pass


def _topological_order(nodes: List[Dict[str, Any]],
                       edges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ids = [n["id"] for n in nodes]
    if len(set(ids)) != len(ids):
        raise FlowError("节点 id 重复")
    node_map = {n["id"]: n for n in nodes}
    indeg = {nid: 0 for nid in ids}
    adj: Dict[str, List[str]] = {nid: [] for nid in ids}
    for e in edges:
        s, t = e["source"], e["target"]
        if s not in node_map or t not in node_map:
            raise FlowError(f"连线端点不存在: {s} -> {t}")
        adj[s].append(t)
        indeg[t] += 1
    queue = [nid for nid in ids if indeg[nid] == 0]
    order: List[str] = []
    while queue:
        nid = queue.pop(0)
        order.append(nid)
        for nxt in adj[nid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    if len(order) != len(ids):
        raise FlowError("节点图中存在环路，无法执行")
    return [node_map[nid] for nid in order]


def run_graph(graph: Dict[str, Any], ctx) -> Dict[str, Dict[str, Any]]:
    """执行代码节点图，返回 {node_id: outputs}。"""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    if not nodes:
        raise FlowError("图中没有节点")
    order = _topological_order(nodes, edges)

    # 记录每个输入端口连了哪些上游输出（多输入时 list）
    inputs_map: Dict[Tuple[str, str], List[Tuple[str, str]]] = {}
    for e in edges:
        key = (e["target"], e["target_port"])
        inputs_map.setdefault(key, []).append((e["source"], e["source_port"]))

    outputs: Dict[str, Dict[str, Any]] = {}
    for node in order:
        type_id = node["type"]
        nd = registry.get_node_def(type_id)
        if nd is None or nd.func is None:
            raise FlowError(f"未知节点类型: {type_id}")
        inputs: Dict[str, Any] = {}
        for port in nd.inputs:
            conns = inputs_map.get((node["id"], port.name), [])
            if not conns:
                if port.required:
                    raise FlowError(f"节点 {node['id']} 缺少输入 {port.name}")
                continue
            values = []
            for src_id, src_port in conns:
                src_out = outputs.get(src_id, {})
                if src_port not in src_out:
                    raise FlowError(
                        f"节点 {src_id} 没有输出端口 {src_port}")
                values.append(src_out[src_port])
            inputs[port.name] = values[0] if len(values) == 1 else values
        params = node.get("params", {})
        ctx.log(f"[节点] {node['id']} ({type_id})")
        outputs[node["id"]] = nd.func(inputs, params, ctx) or {}
    return outputs
