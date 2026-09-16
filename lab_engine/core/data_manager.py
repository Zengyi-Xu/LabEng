"""运行数据管理。

负责生成 run_id、创建运行目录、保存 CSV 和 JSON 元数据。
"""
import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


logger = logging.getLogger("lab_engine.data_manager")


class DataManager:
    """数据管理器。"""

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def new_run(self, routine_name: str) -> Tuple[str, Path]:
        """创建新的运行目录，返回 (run_id, run_dir)。"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in routine_name)
        run_id = f"{ts}_{safe_name}"
        run_dir = self.base_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created run directory: {run_dir}")
        return run_id, run_dir

    def save_csv(self, run_dir: Path, points: List[Dict[str, Any]], filename: str = "data.csv") -> Path:
        """把数据点列表保存为 CSV。允许不同 point 有不同字段，取并集。"""
        if not points:
            logger.warning("No points to save")
            return run_dir / filename

        path = run_dir / filename
        fieldnames = sorted({k for p in points for k in p.keys()})
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, restval="")
            writer.writeheader()
            for row in points:
                writer.writerow(row)
        logger.info(f"Saved CSV: {path}")
        return path

    def save_metadata(
        self,
        run_dir: Path,
        routine_name: str,
        routine_path: Path,
        params: Dict[str, Any],
        instruments: Dict[str, Dict[str, Any]],
        filename: str = "metadata.json",
    ) -> Path:
        """保存运行元数据。"""
        path = run_dir / filename
        metadata = {
            "run_id": run_dir.name,
            "routine_name": routine_name,
            "routine_path": str(routine_path),
            "saved_at": datetime.now().isoformat(),
            "params": params,
            "instruments": instruments,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"Saved metadata: {path}")
        return path

    def list_runs(self) -> List[Dict[str, Any]]:
        """列出所有已保存的运行目录。"""
        runs = []
        if not self.base_dir.is_dir():
            return runs
        for p in sorted(self.base_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if p.is_dir():
                meta_path = p / "metadata.json"
                info = {"run_id": p.name, "path": str(p)}
                if meta_path.is_file():
                    try:
                        info["metadata"] = json.loads(meta_path.read_text(encoding="utf-8"))
                    except Exception:
                        pass
                runs.append(info)
        return runs
