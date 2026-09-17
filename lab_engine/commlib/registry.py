"""汇总三套通信节点库，对外提供统一的 NODES 注册表。

每个子包（dmt / cap / superposition）都维护自己的 NODES；
这里在导入时合并，前缀 type_id 避免冲突（如 dmt.bit_source）。
"""
from typing import Any, Dict, List, Optional

from lab_engine.commlib import cap, dmt  # noqa: F401

LIBRARIES = ["dmt", "cap"]

NODES: Dict[str, Any] = {}
CATEGORY_COLORS: Dict[str, str] = {}


def _merge(lib: str, module) -> None:
    for type_id, node_def in module.NODES.items():
        key = f"{lib}.{type_id}"
        # 复制一份并把 type_id 改成带前缀的全局 ID
        import copy
        nd = copy.copy(node_def)
        nd.type_id = key
        NODES[key] = nd
    for cat, color in module.CATEGORY_COLORS.items():
        CATEGORY_COLORS.setdefault(cat, color)


_merge("dmt", dmt.nodes)
_merge("cap", cap.nodes)


def libraries() -> List[str]:
    return list(LIBRARIES)


def get_node_def(type_id: str):
    return NODES.get(type_id)


def node_types_by_category() -> Dict[str, list]:
    out: Dict[str, list] = {}
    for nd in NODES.values():
        out.setdefault(nd.category, []).append(nd)
    return out
