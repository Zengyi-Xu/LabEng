"""例程参数持久化。

以例程 NAME 为 key，把用户最后使用的参数值保存为 JSON 文件，
下次加载同一例程时优先恢复这些值，而不是 PARAMS 里的默认值。
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional


logger = logging.getLogger("lab_engine.param_store")


class ParamStore:
    """基于 JSON 文件的例程参数存储。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._data: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self._data = {}
            return
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"Failed to load param store {self.path}: {exc}")
            self._data = {}

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning(f"Failed to save param store {self.path}: {exc}")

    def get(self, routine_name: str) -> Dict[str, Any]:
        return dict(self._data.get(routine_name, {}))

    def set(self, routine_name: str, values: Dict[str, Any]) -> None:
        if not routine_name:
            return
        self._data[routine_name] = dict(values)
        self.save()

    def update(self, routine_name: str, name: str, value: Any) -> None:
        if not routine_name:
            return
        self._data.setdefault(routine_name, {})[name] = value
        self.save()
