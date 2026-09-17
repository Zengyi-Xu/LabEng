"""测试系统注册表。

把两类来源统一成「测试系统」：
- ``kind == "routine"``：``lab_engine/routines/`` 下的 .py 例程，本身即一个
  单位测试系统（只包含一个测量任务）。
- ``kind == "setup"``   ：``*.labsetup.json`` 组合系统，包含 host/comm/
  instrument/routine 节点，可包含多个测量任务。
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from lab_engine.core.registry import RoutineMeta, RoutineRegistry
from lab_engine.core.setup_graph import SetupGraph


logger = logging.getLogger("lab_engine.system_registry")


@dataclass
class SystemTask:
    """组合系统中的一个测量任务（routine 节点）。"""
    node_id: str
    label: str
    routine_name: str
    panel_cfg: Optional[Dict[str, Any]] = None


@dataclass
class SystemMeta:
    """测试系统元数据。"""
    name: str
    kind: str  # "routine" | "setup"
    path: Path
    description: str = ""
    routine: Optional[RoutineMeta] = None
    graph: Optional[SetupGraph] = None
    _tasks: Optional[List[SystemTask]] = None

    @property
    def is_setup(self) -> bool:
        return self.kind == "setup"

    def tasks(self) -> List[SystemTask]:
        """返回组合系统中的测量任务列表；单位系统返回空列表。"""
        if self._tasks is not None:
            return self._tasks
        tasks: List[SystemTask] = []
        if self.graph is not None:
            for node in self.graph.nodes_by_type("routine"):
                routine_name = node.data.get("template") or node.data.get("routine_name") or ""
                if not routine_name:
                    continue
                tasks.append(SystemTask(
                    node_id=node.node_id,
                    label=node.label or routine_name,
                    routine_name=routine_name,
                    panel_cfg=node.data.get("panel_cfg"),
                ))
        self._tasks = tasks
        return tasks


class SystemRegistry:
    """扫描 .py 例程与 .labsetup.json 项目，统一提供给 GUI。"""

    def __init__(self, routine_registry: RoutineRegistry):
        self.routine_registry = routine_registry
        self._systems: Dict[str, SystemMeta] = {}
        self._paths: List[Path] = []
        self.last_report: Dict[str, Any] = {"loaded": [], "failed": []}

    def discover(self, setup_paths: List[Path]) -> None:
        self._paths = list(setup_paths)
        self._systems.clear()
        self.last_report = {"loaded": [], "failed": []}

        # 1) .py 例程 → 单位测试系统
        for routine in self.routine_registry.list():
            name = f"[例程] {routine.name}"
            self._systems[name] = SystemMeta(
                name=name,
                kind="routine",
                path=routine.path,
                description=routine.description,
                routine=routine,
            )
            self.last_report["loaded"].append(name)

        # 2) .labsetup.json → 组合测试系统
        for base in setup_paths:
            if not base.is_dir():
                continue
            for json_file in sorted(base.rglob("*.labsetup.json")):
                try:
                    graph = SetupGraph.load(json_file)
                    name = json_file.name[: -len(".labsetup.json")]
                    self._systems[name] = SystemMeta(
                        name=name,
                        kind="setup",
                        path=json_file,
                        description=f"组合系统（{len(graph.nodes)} 节点 / {len(graph.edges)} 连线）",
                        graph=graph,
                    )
                    self.last_report["loaded"].append(name)
                except Exception as exc:
                    logger.warning(f"Failed to load setup project {json_file}: {exc}")
                    self.last_report["failed"].append(f"{json_file.name}: {exc}")

    def refresh(self) -> None:
        self.routine_registry.refresh()
        if self._paths:
            self.discover(self._paths)

    def get(self, name: str) -> Optional[SystemMeta]:
        return self._systems.get(name)

    def list(self) -> List[SystemMeta]:
        return list(self._systems.values())

    def names(self) -> List[str]:
        return list(self._systems.keys())
