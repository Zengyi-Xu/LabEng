"""数据保存与处理"""
import csv
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

import numpy as np

from .iv_scanner import ScanResult
from .hysteresis import HysteresisResult
from ..core.logger import setup_logger


class DataHandler:
    """数据处理与保存器"""

    def __init__(self, output_dir: str = "./data", logger=None):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger or setup_logger("data")

    def _generate_filename(self, prefix: str = "iv_scan", suffix: str = ".csv") -> str:
        """生成带时间戳的文件名"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{prefix}_{ts}{suffix}"

    def save_scan_result(self, result: ScanResult, filename: Optional[str] = None,
                         prefix: str = "iv_scan") -> str:
        """保存单次扫描结果到CSV"""
        if filename is None:
            filename = self._generate_filename(prefix)

        filepath = self.output_dir / filename

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # 元数据头
            writer.writerow(["# IV Scan Result"])
            writer.writerow(["# Direction", result.direction])
            for k, v in result.metadata.items():
                writer.writerow([f"# {k}", v])
            writer.writerow([])  # 空行

            # 数据表头
            writer.writerow(["Voltage(V)", "Current(A)", "Resistance(Ohm)", "Time(s)"])

            # 数据
            for v, i, r, t in zip(result.voltages, result.currents, 
                                   result.resistances, result.timestamps):
                writer.writerow([f"{v:.6e}", f"{i:.6e}", f"{r:.6e}", f"{t:.6f}"])

        self.logger.info(f"扫描数据已保存: {filepath}")
        return str(filepath)

    def save_multiple_results(self, results: List[ScanResult], 
                              prefix: str = "iv_scan") -> List[str]:
        """保存多次扫描结果"""
        files = []
        for idx, result in enumerate(results):
            fname = self._generate_filename(f"{prefix}_run{idx+1}")
            fpath = self.save_scan_result(result, fname, prefix)
            files.append(fpath)
        return files

    def save_averaged_result(self, result: ScanResult, 
                             prefix: str = "iv_avg") -> str:
        """保存平均后的结果"""
        return self.save_scan_result(result, prefix=prefix)

    def save_hysteresis_result(self, h_result: HysteresisResult,
                               prefix: str = "hysteresis") -> str:
        """保存回滞分析结果"""
        filename = self._generate_filename(prefix)
        filepath = self.output_dir / filename

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["# Hysteresis Analysis"])
            writer.writerow(["# Hysteresis Area", h_result.hysteresis_area])
            writer.writerow(["# Hysteresis Index", h_result.hysteresis_index])
            writer.writerow(["# Max Delta I", h_result.delta_i_max])
            writer.writerow(["# Symmetry Factor", h_result.symmetry_factor])
            writer.writerow([])

            writer.writerow(["Voltage(V)", "Forward_I(A)", "Backward_I(A)", "Delta_I(A)"])
            for v, i_f, i_b, d_i in zip(h_result.voltage_grid,
                                         h_result.forward_i,
                                         h_result.backward_i,
                                         h_result.delta_i):
                writer.writerow([f"{v:.6e}", f"{i_f:.6e}", f"{i_b:.6e}", f"{d_i:.6e}"])

        self.logger.info(f"回滞数据已保存: {filepath}")
        return str(filepath)

    def save_wavelength_scan(self, results: List["WavelengthScanResult"],
                             prefix: str = "wavelength_scan") -> str:
        """保存波长扫描结果到CSV，多方向结果写入同一文件"""
        from .wavelength_scanner import WavelengthScanResult  # noqa: F401
        filename = self._generate_filename(prefix)
        filepath = self.output_dir / filename

        has_power = any(r.powers is not None for r in results)

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["# Wavelength Scan"])
            for k, v in results[0].metadata.items():
                writer.writerow([f"# {k}", v])
            writer.writerow([])

            header = ["Direction", "Wavelength_requested(nm)", "Wavelength_actual(nm)"]
            if has_power:
                header.append("Power")
            header.append("Time(s)")
            writer.writerow(header)

            for r in results:
                for i in range(len(r.wavelengths)):
                    row = [r.direction,
                           f"{r.wavelengths[i]:.4f}",
                           f"{r.actual[i]:.4f}"]
                    if has_power:
                        if r.powers is not None:
                            row.append(f"{r.powers[i]:.6e}")
                        else:
                            row.append("")
                    row.append(f"{r.timestamps[i]:.3f}")
                    writer.writerow(row)

        self.logger.info(f"波长扫描数据已保存: {filepath}")
        return str(filepath)

    def save_summary(self, metadata: dict, filename: str = "summary.json") -> str:
        """保存实验摘要JSON"""
        filepath = self.output_dir / filename
        metadata["saved_at"] = datetime.now().isoformat()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        return str(filepath)
