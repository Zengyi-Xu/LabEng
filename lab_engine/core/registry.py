"""仪器与例程注册表。

提供两类注册表：
- InstrumentRegistry：注册仪器类及其连接参数 schema。
- RoutineRegistry：从目录动态发现例程插件。
"""
import importlib.util
import inspect
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type


logger = logging.getLogger("lab_engine.registry")


@dataclass
class InstrumentMeta:
    """仪器元数据。"""
    key: str
    cls: Type
    name: str
    connection_params: List[Dict[str, Any]] = field(default_factory=list)
    description: str = ""


class InstrumentRegistry:
    """仪器注册表。"""

    _registry: Dict[str, InstrumentMeta] = {}

    @classmethod
    def register(
        cls,
        key: str,
        cls_type: Type,
        name: str,
        connection_params: Optional[List[Dict[str, Any]]] = None,
        description: str = "",
    ) -> None:
        """注册一个仪器类。"""
        key = key.lower().strip()
        if key in cls._registry:
            logger.warning(f"Instrument '{key}' already registered; overwriting")
        cls._registry[key] = InstrumentMeta(
            key=key,
            cls=cls_type,
            name=name,
            connection_params=connection_params or [],
            description=description,
        )
        logger.debug(f"Registered instrument: {key}")

    @classmethod
    def get(cls, key: str) -> Optional[InstrumentMeta]:
        return cls._registry.get(key.lower().strip())

    @classmethod
    def list(cls) -> List[InstrumentMeta]:
        return list(cls._registry.values())

    @classmethod
    def keys(cls) -> List[str]:
        return list(cls._registry.keys())

    @classmethod
    def clear(cls) -> None:
        cls._registry.clear()


@dataclass
class RoutineMeta:
    """例程元数据。"""
    name: str
    module_name: str
    path: Path
    module: Any
    description: str = ""
    icon: str = ""
    instruments: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    params: List[Dict[str, Any]] = field(default_factory=list)
    outputs: List[Dict[str, Any]] = field(default_factory=list)
    setup_graph: Optional[Dict[str, Any]] = None  # SETUP_GRAPH：保存时的框图快照
    panel: Optional[Dict[str, Any]] = None        # PANEL：操作面板描述

    @property
    def run(self) -> Callable:
        return getattr(self.module, "run")


class RoutineRegistry:
    """例程注册表：从目录扫描 .py 例程文件。"""

    def __init__(self):
        self._routines: Dict[str, RoutineMeta] = {}
        self._paths: List[Path] = []
        # 最近一次扫描的报告（供 GUI 显示加载失败原因）
        self.last_report: Dict[str, Any] = {"loaded": [], "failed": [], "duplicates": []}

    def discover(self, paths: List[Path]) -> None:
        """递归扫描给定目录下的 .py 文件并加载为例程。"""
        self._paths = list(paths)
        self._routines.clear()
        self.last_report = {"loaded": [], "failed": [], "duplicates": []}
        for path in paths:
            if not path.is_dir():
                logger.warning(f"Routine path is not a directory: {path}")
                continue
            for py_file in sorted(path.rglob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                try:
                    meta = self._load_routine(py_file)
                    if meta:
                        if meta.name in self._routines:
                            logger.warning(
                                f"Duplicate routine name '{meta.name}' in {py_file}; "
                                f"overrides {self._routines[meta.name].path}"
                            )
                            self.last_report["duplicates"].append(
                                f"{meta.name}（{py_file.name} 覆盖了 "
                                f"{self._routines[meta.name].path.name}）"
                            )
                        self._routines[meta.name] = meta
                        self.last_report["loaded"].append(meta.name)
                except Exception as exc:
                    logger.warning(f"Failed to load routine {py_file}: {exc}")
                    self.last_report["failed"].append(f"{py_file.name}: {exc}")

    def _load_routine(self, py_file: Path) -> Optional[RoutineMeta]:
        module_name = f"lab_engine_routine_{py_file.stem}"
        spec = importlib.util.spec_from_file_location(module_name, py_file)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        required_attrs = ("NAME", "PARAMS", "run")
        for attr in required_attrs:
            if not hasattr(module, attr):
                logger.debug(f"{py_file} missing '{attr}', skipping")
                return None

        if not inspect.isfunction(getattr(module, "run")):
            logger.warning(f"{py_file}: 'run' is not callable")
            return None

        name = str(getattr(module, "NAME"))
        return RoutineMeta(
            name=name,
            module_name=module_name,
            path=py_file,
            module=module,
            description=getattr(module, "DESCRIPTION", ""),
            icon=getattr(module, "ICON", ""),
            instruments=getattr(module, "INSTRUMENTS", {}),
            params=list(getattr(module, "PARAMS", [])),
            outputs=list(getattr(module, "OUTPUTS", [])),
            setup_graph=getattr(module, "SETUP_GRAPH", None),
            panel=getattr(module, "PANEL", None),
        )

    def get(self, name: str) -> Optional[RoutineMeta]:
        return self._routines.get(name)

    def list(self) -> List[RoutineMeta]:
        return list(self._routines.values())

    def names(self) -> List[str]:
        return list(self._routines.keys())

    def refresh(self) -> None:
        """使用上一次指定的路径重新扫描例程。"""
        if self._paths:
            self.discover(self._paths)
