"""例程运行时上下文。

每个例程在后台线程中运行时，都会拿到一个 RoutineContext 实例。
它通过线程安全的 queue 与 GUI 通信，并提供停止检查接口。
"""
import queue
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional


class RoutineContext:
    """例程运行时上下文。"""

    def __init__(
        self,
        run_id: str,
        output_dir: Path,
        msg_queue: queue.Queue,
        stop_event: threading.Event,
    ):
        self.run_id = run_id
        self.output_dir = output_dir
        self._msg_queue = msg_queue
        self._stop_event = stop_event
        self._points: list[Dict[str, Any]] = []
        self._start_time = time.time()

    # ── 与 GUI 通信 ──────────────────────────────────────────────

    def log(self, text: str, level: str = "info") -> None:
        """发送日志消息到 GUI。"""
        self._msg_queue.put(("log", {"text": str(text), "level": level}))

    def progress(self, current: float, total: float) -> None:
        """更新进度（current/total 可以是任意数值）。"""
        self._msg_queue.put(
            ("progress", {"current": float(current), "total": float(total)})
        )

    def point(self, **kwargs: Any) -> None:
        """上报一个数据点，GUI 会实时绘制。"""
        self._points.append(dict(kwargs))
        self._msg_queue.put(("point", dict(kwargs)))

    def data(self, **kwargs: Any) -> None:
        """上报最终聚合数据。"""
        self._msg_queue.put(("data", dict(kwargs)))

    def error(self, text: str) -> None:
        """上报错误。"""
        self._msg_queue.put(("log", {"text": str(text), "level": "error"}))

    def done(self, success: bool = True) -> None:
        """例程结束时调用。"""
        self._msg_queue.put(("done", {"success": bool(success)}))

    # ── 停止检查 ─────────────────────────────────────────────────

    def is_stopped(self) -> bool:
        """返回用户是否请求停止。"""
        return self._stop_event.is_set()

    def elapsed(self) -> float:
        """返回例程已运行时间（秒）。"""
        return time.time() - self._start_time

    # ── 数据访问 ─────────────────────────────────────────────────

    @property
    def points(self) -> list[Dict[str, Any]]:
        return list(self._points)
