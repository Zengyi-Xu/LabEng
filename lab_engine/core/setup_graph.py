"""Lab Engine Setup 框图数据模型。

用节点（Node）和边（Edge）描述一个实验系统：
- host       : 上位机，输出 control
- comm       : 通信接口/协议，输入 control，输出 comm
- instrument : 仪器，输入 comm，输出 data
- routine    : 例程，输入所需的 instrument data

SetupGraph 负责序列化、反序列化以及基础合法性校验。
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import uuid


# 节点默认尺寸（像素）
NODE_WIDTH = 160
NODE_HEIGHT = 80
PORT_RADIUS = 6


@dataclass
class Port:
    """节点端口。"""
    name: str
    label: str
    direction: str  # "input" | "output"
    data_type: str = "any"  # 用于连线匹配

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "direction": self.direction,
            "data_type": self.data_type,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Port":
        return cls(
            name=d["name"],
            label=d.get("label", d["name"]),
            direction=d["direction"],
            data_type=d.get("data_type", "any"),
        )


@dataclass
class Node:
    """Setup 图节点。"""
    node_id: str
    node_type: str  # host | comm | instrument | routine
    x: float = 100.0
    y: float = 100.0
    label: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    ports: List[Port] = field(default_factory=list)

    def __post_init__(self):
        if not self.label:
            self.label = self.node_type.capitalize()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.node_id,
            "type": self.node_type,
            "x": self.x,
            "y": self.y,
            "label": self.label,
            # 以下划线开头的键是运行时状态（如 _template_routine 对象引用），
            # 不可序列化也不属于持久化内容
            "data": {k: v for k, v in self.data.items() if not k.startswith("_")},
            "ports": [p.to_dict() for p in self.ports],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Node":
        return cls(
            node_id=d["id"],
            node_type=d["type"],
            x=d.get("x", 100.0),
            y=d.get("y", 100.0),
            label=d.get("label", ""),
            data=dict(d.get("data", {})),
            ports=[Port.from_dict(p) for p in d.get("ports", [])],
        )

    def port(self, name: str) -> Optional[Port]:
        for p in self.ports:
            if p.name == name:
                return p
        return None


@dataclass
class Edge:
    """Setup 图连线。"""
    edge_id: str
    source_node: str
    source_port: str
    target_node: str
    target_port: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.edge_id,
            "source_node": self.source_node,
            "source_port": self.source_port,
            "target_node": self.target_node,
            "target_port": self.target_port,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Edge":
        return cls(
            edge_id=d["id"],
            source_node=d["source_node"],
            source_port=d["source_port"],
            target_node=d["target_node"],
            target_port=d["target_port"],
        )


class SetupGraph:
    """Setup 图：节点 + 连线的集合。"""

    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.edges: Dict[str, Edge] = {}

    # ------------------------------------------------------------------
    # 节点操作
    # ------------------------------------------------------------------
    def add_node(self, node_type: str, x: float, y: float,
                 label: Optional[str] = None,
                 data: Optional[Dict[str, Any]] = None,
                 node_id: Optional[str] = None) -> Node:
        node_id = node_id or _new_id("n")
        node = Node(
            node_id=node_id,
            node_type=node_type,
            x=x,
            y=y,
            label=label or _default_label(node_type),
            data=data or {},
            ports=_default_ports(node_type),
        )
        self.nodes[node_id] = node
        return node

    def remove_node(self, node_id: str) -> None:
        """删除节点及其所有连线。"""
        if node_id in self.nodes:
            del self.nodes[node_id]
        to_remove = [
            eid for eid, e in self.edges.items()
            if e.source_node == node_id or e.target_node == node_id
        ]
        for eid in to_remove:
            del self.edges[eid]

    def get_node(self, node_id: str) -> Optional[Node]:
        return self.nodes.get(node_id)

    def nodes_by_type(self, node_type: str) -> List[Node]:
        return [n for n in self.nodes.values() if n.node_type == node_type]

    # ------------------------------------------------------------------
    # 状态覆盖（供外部同步连接状态等）
    # ------------------------------------------------------------------
    def set_node_status_override(self, node_id: str, status: str, message: str = "") -> None:
        """外部设置节点状态覆盖（如仪器连接成功/失败）。

        status: "normal" | "warning" | "error" | "synced"
        """
        node = self.nodes.get(node_id)
        if node is not None:
            node.data["_status_override"] = status
            node.data["_status_override_msg"] = message

    def clear_node_status_override(self, node_id: str) -> None:
        node = self.nodes.get(node_id)
        if node is not None:
            node.data.pop("_status_override", None)
            node.data.pop("_status_override_msg", None)

    # ------------------------------------------------------------------
    # 边操作
    # ------------------------------------------------------------------
    def add_edge(self, source_node: str, source_port: str,
                 target_node: str, target_port: str,
                 edge_id: Optional[str] = None,
                 allow_multi_input: bool = False) -> Optional[Edge]:
        """添加一条边，若连接非法则返回 None。

        allow_multi_input: 为 True 时允许同一 input 端口连接多条边，
        用于代码依赖图等多对一场景。
        """
        src = self.get_node(source_node)
        dst = self.get_node(target_node)
        if src is None or dst is None:
            return None
        src_port = src.port(source_port)
        dst_port = dst.port(target_port)
        if src_port is None or dst_port is None:
            return None
        if src_port.direction != "output" or dst_port.direction != "input":
            return None

        # 避免同一 input 端口被重复连接
        if not allow_multi_input:
            for e in self.edges.values():
                if e.target_node == target_node and e.target_port == target_port:
                    return None

        edge = Edge(
            edge_id=edge_id or _new_id("e"),
            source_node=source_node,
            source_port=source_port,
            target_node=target_node,
            target_port=target_port,
        )
        self.edges[edge.edge_id] = edge
        return edge

    def remove_edge(self, edge_id: str) -> None:
        if edge_id in self.edges:
            del self.edges[edge_id]

    def edges_connected_to_node(self, node_id: str) -> List[Edge]:
        return [
            e for e in self.edges.values()
            if e.source_node == node_id or e.target_node == node_id
        ]

    def get_source(self, node_id: str, port_name: str) -> Optional[Tuple[Node, Port]]:
        """获取某个 input 端口的来源节点/端口。"""
        for e in self.edges.values():
            if e.target_node == node_id and e.target_port == port_name:
                src = self.get_node(e.source_node)
                src_port = src.port(e.source_port) if src else None
                if src and src_port:
                    return src, src_port
        return None

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": 1,
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges.values()],
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SetupGraph":
        graph = cls()
        for nd in d.get("nodes", []):
            node = Node.from_dict(nd)
            graph.nodes[node.node_id] = node
        for ed in d.get("edges", []):
            edge = Edge.from_dict(ed)
            graph.edges[edge.edge_id] = edge
        return graph

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                        encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "SetupGraph":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------
    def validate(self) -> List[str]:
        """返回错误信息列表；空列表表示通过。"""
        status_map = self.validate_status()
        errors = []
        for node_id, info in status_map.items():
            if info["status"] == "error":
                errors.append(f"{info['label']}: {info['message']}")
        return errors

    def validate_status(self) -> Dict[str, Dict[str, Any]]:
        """返回每个节点的状态字典。

        格式: {node_id: {"status": "normal|warning|error|synced", "label": str, "message": str}}
        外部覆盖优先于自动校验。
        """
        status: Dict[str, Dict[str, Any]] = {}

        for node in self.nodes.values():
            status[node.node_id] = {
                "status": "normal",
                "label": node.label,
                "message": "",
            }

        for e in self.edges.values():
            src = self.get_node(e.source_node)
            dst = self.get_node(e.target_node)
            if src is None or dst is None:
                continue
            if src.port(e.source_port) is None or dst.port(e.target_port) is None:
                status[dst.node_id] = {
                    "status": "error",
                    "label": dst.label,
                    "message": f"端口 {e.target_port} 不存在",
                }

        # 每个 routine 节点的输入仪器是否已连接
        for node in self.nodes_by_type("routine"):
            missing = []
            for port in node.ports:
                if port.direction == "input" and not self.get_source(node.node_id, port.name):
                    alias = port.name.replace("inst_", "")
                    missing.append(alias)
            if missing:
                status[node.node_id] = {
                    "status": "error",
                    "label": node.label,
                    "message": f"缺少仪器连接: {', '.join(missing)}",
                }

        # 每个 instrument 节点是否连到了 comm
        for node in self.nodes_by_type("instrument"):
            if not self.get_source(node.node_id, "comm"):
                status[node.node_id] = {
                    "status": "warning",
                    "label": node.label,
                    "message": "未连接通信接口",
                }

        # 没有连线的 comm/host 节点
        for node in self.nodes_by_type("host"):
            if not any(e.source_node == node.node_id for e in self.edges.values()):
                status[node.node_id] = {
                    "status": "warning",
                    "label": node.label,
                    "message": "未连接到通信接口",
                }
        for node in self.nodes_by_type("comm"):
            has_input = any(e.target_node == node.node_id for e in self.edges.values())
            has_output = any(e.source_node == node.node_id for e in self.edges.values())
            if not has_input:
                status[node.node_id] = {
                    "status": "warning",
                    "label": node.label,
                    "message": "缺少输入连接",
                }
            elif not has_output:
                status[node.node_id] = {
                    "status": "warning",
                    "label": node.label,
                    "message": "未连接到任何仪器",
                }

        # 外部覆盖优先
        for node in self.nodes.values():
            override = node.data.get("_status_override")
            if override:
                status[node.node_id] = {
                    "status": override,
                    "label": node.label,
                    "message": node.data.get("_status_override_msg", ""),
                }

        return status


# ----------------------------------------------------------------------
# 辅助函数
# ----------------------------------------------------------------------
def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _default_label(node_type: str) -> str:
    return {
        "host": "上位机",
        "comm": "通信接口",
        "instrument": "仪器",
        "routine": "例程",
        "text": "双击编辑文本",
    }.get(node_type, node_type.capitalize())


def _default_ports(node_type: str) -> List[Port]:
    if node_type == "host":
        return [Port("control", "控制", "output", "control")]
    if node_type == "comm":
        return [
            Port("control", "控制", "input", "control"),
            Port("comm", "通信", "output", "comm"),
        ]
    if node_type == "instrument":
        return [
            Port("comm", "通信", "input", "comm"),
            Port("data", "数据", "output", "data"),
        ]
    if node_type == "routine":
        return []
    return []
