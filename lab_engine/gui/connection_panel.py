"""仪器连接面板：根据例程声明自动渲染连接 UI。"""
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable, Dict, List, Optional

from lab_engine.core.registry import InstrumentMeta, InstrumentRegistry
from lab_engine.gui.shell import COLOR_BG, COLOR_CARD, COLOR_TEXT_DIM, UI_FONT


class _InstrumentWorker(threading.Thread):
    """后台线程：持有单个仪器实例，处理连接/断开/轮询。"""

    def __init__(self, meta: InstrumentMeta, state: Dict[str, Any],
                 cmd_queue: queue.Queue, msg_queue: queue.Queue):
        super().__init__(daemon=True)
        self.meta = meta
        self.state = state
        self.cmd_queue = cmd_queue
        self.msg_queue = msg_queue
        self.inst: Optional[Any] = None
        self._running = True
        self.connected = False

    def run(self):
        while self._running:
            try:
                cmd = self.cmd_queue.get_nowait()
                self._handle_cmd(cmd)
            except queue.Empty:
                pass

            if self.connected and self.inst is not None and hasattr(self.inst, "measure"):
                try:
                    data = self.inst.measure()
                    self.state["reading"] = data
                    self.state["error"] = ""
                except Exception as exc:
                    self.state["error"] = str(exc)

            time.sleep(0.25)

        self._disconnect()

    def _handle_cmd(self, cmd: tuple):
        if cmd[0] == "connect":
            _, kwargs = cmd
            self._connect(kwargs)
        elif cmd[0] == "disconnect":
            self._disconnect()
        elif cmd[0] == "stop":
            self._running = False

    def _connect(self, kwargs: Dict[str, Any]):
        if self.connected:
            return
        try:
            self.inst = self.meta.cls(**kwargs)
            self.inst.connect(retries=2)
            self.connected = True
            self.state["connected"] = True
            self.state["idn"] = self.inst.idn() if hasattr(self.inst, "idn") else ""
            self.state["error"] = ""
            self.msg_queue.put(("log", {"text": f"{self.meta.name} 已连接", "level": "info"}))
        except Exception as exc:
            self.connected = False
            self.inst = None
            self.state["connected"] = False
            self.state["error"] = str(exc)
            self.msg_queue.put(("log", {"text": f"{self.meta.name} 连接失败: {exc}", "level": "error"}))

    def _disconnect(self):
        if self.inst is not None:
            try:
                self.inst.disconnect()
            except Exception as exc:
                self.msg_queue.put(("log", {"text": f"{self.meta.name} 断开出错: {exc}", "level": "warn"}))
            finally:
                self.inst = None
        self.connected = False
        self.state["connected"] = False
        self.state["idn"] = ""
        self.state["reading"] = None
        self.state["error"] = ""


class _InstrumentCard(tk.Frame):
    """单个仪器的连接卡片。"""

    def __init__(self, parent, alias: str, meta: InstrumentMeta,
                 msg_queue: queue.Queue, on_change: Optional[Callable] = None,
                 on_connection_change: Optional[Callable[[str, bool], None]] = None):
        super().__init__(parent, bg=COLOR_CARD,
                         highlightbackground="#E2E8F0", highlightthickness=1, bd=0)
        self.alias = alias
        self.meta = meta
        self.msg_queue = msg_queue
        self.on_change = on_change
        self.on_connection_change = on_connection_change
        self._last_connected = False
        self.state = {
            "connected": False,
            "idn": "",
            "reading": None,
            "error": "",
        }
        self.cmd_queue: queue.Queue = queue.Queue()
        self.worker: Optional[_InstrumentWorker] = None
        self.param_vars: Dict[str, tk.Variable] = {}
        self._setup_ui()
        self._start_worker()

    def _setup_ui(self):
        pad = 10
        inner = tk.Frame(self, bg=COLOR_CARD)
        inner.pack(fill=tk.X, padx=pad, pady=pad)

        # 标题行
        hdr = tk.Frame(inner, bg=COLOR_CARD)
        hdr.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(hdr, text=f"{self.meta.name} ({self.alias})",
                  style="Section.TLabel").pack(side=tk.LEFT)
        self.status_lbl = ttk.Label(hdr, text="未连接", foreground="gray")
        self.status_lbl.pack(side=tk.RIGHT)

        # 连接参数
        self.params_frame = tk.Frame(inner, bg=COLOR_CARD)
        self.params_frame.pack(fill=tk.X, pady=2)
        for p in self.meta.connection_params:
            self._make_param_widget(p)

        # IDN / 读数
        self.idn_lbl = ttk.Label(inner, text="IDN: --", wraplength=360,
                                 style="DimCard.TLabel")
        self.idn_lbl.pack(anchor=tk.W, pady=(4, 2))

        self.read_lbl = ttk.Label(inner, text="读数: --")
        self.read_lbl.pack(anchor=tk.W, pady=(0, 6))

        # 按钮
        self.conn_btn = ttk.Button(inner, text="连接", command=self._toggle_connect)
        self.conn_btn.pack(anchor=tk.W)

    def _make_param_widget(self, p: Dict[str, Any]):
        name = p["name"]
        label = p.get("label", name)
        ptype = p.get("type", "float")
        default = p.get("default", "")

        row = tk.Frame(self.params_frame, bg=COLOR_CARD)
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=f"{label}:", width=14).pack(side=tk.LEFT)

        if ptype == "choice":
            var = tk.StringVar(value=str(default))
            combo = ttk.Combobox(row, textvariable=var, values=p.get("choices", []),
                                 state="readonly", width=14)
            combo.pack(side=tk.LEFT)
        elif ptype == "bool":
            var = tk.BooleanVar(value=bool(default))
            ttk.Checkbutton(row, variable=var, text="启用").pack(side=tk.LEFT)
        elif ptype == "port":
            var = tk.StringVar(value=str(default))
            self.param_vars[name] = var  # 必须先注册，_refresh_ports 会用到
            combo = ttk.Combobox(row, textvariable=var, values=[], width=28)
            combo.pack(side=tk.LEFT)
            ttk.Button(row, text="⟳", width=3, command=self._refresh_ports).pack(side=tk.LEFT, padx=(4, 0))
            self._port_combo = combo
            self._refresh_ports()
            return
        elif ptype == "int":
            var = tk.IntVar(value=int(default) if str(default).replace("-", "").isdigit() else 0)
            ttk.Entry(row, textvariable=var, width=16).pack(side=tk.LEFT)
        elif ptype == "float":
            var = tk.DoubleVar(value=float(default) if default != "" else 0.0)
            ttk.Entry(row, textvariable=var, width=16).pack(side=tk.LEFT)
        else:
            var = tk.StringVar(value=str(default))
            ttk.Entry(row, textvariable=var, width=24).pack(side=tk.LEFT)

        self.param_vars[name] = var

    def _refresh_ports(self):
        try:
            import serial.tools.list_ports
            ports = [f"{p.device} - {p.description}" for p in serial.tools.list_ports.comports()]
        except Exception:
            ports = []
        if hasattr(self, "_port_combo"):
            current = self.param_vars.get("port", tk.StringVar()).get()
            self._port_combo["values"] = ports
            if ports and not current:
                self.param_vars["port"].set(ports[0].split(" - ")[0])

    def _get_connection_kwargs(self) -> Dict[str, Any]:
        kwargs = {}
        for p in self.meta.connection_params:
            name = p["name"]
            var = self.param_vars.get(name)
            if var is None:
                continue
            ptype = p.get("type", "float")
            raw = var.get()
            if ptype == "port":
                # 从 "COM3 - USB Serial" 中提取 "COM3"
                raw = str(raw).split(" - ")[0].strip()
            elif ptype == "int":
                raw = int(raw)
            elif ptype == "float":
                raw = float(raw)
            kwargs[name] = raw
        return kwargs

    def _toggle_connect(self):
        if self.state["connected"]:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        kwargs = self._get_connection_kwargs()
        if not kwargs.get("port"):
            messagebox.showwarning("提示", f"请先选择 {self.meta.name} 的端口")
            return
        self.cmd_queue.put(("connect", kwargs))

    def disconnect(self):
        self.cmd_queue.put(("disconnect",))

    def _start_worker(self):
        self.worker = _InstrumentWorker(self.meta, self.state, self.cmd_queue, self.msg_queue)
        self.worker.start()

    def stop_worker(self):
        if self.worker is not None:
            self.cmd_queue.put(("stop",))

    def set_enabled(self, enabled: bool):
        """启用或禁用连接按钮。"""
        state = tk.NORMAL if enabled else tk.DISABLED
        self.conn_btn.configure(state=state)
        for p in self.meta.connection_params:
            name = p["name"]
            var = self.param_vars.get(name)
            if var is None:
                continue
            ptype = p.get("type", "float")
            # ttk Combobox/Entry 没有直接句柄，简单处理：只禁用连接按钮
            # 后续可扩展为禁用所有参数控件
        if hasattr(self, "_port_combo"):
            self._port_combo.configure(state="readonly" if enabled else tk.DISABLED)

    def get_instance(self) -> Optional[Any]:
        return self.worker.inst if self.worker and self.worker.connected else None

    def is_connected(self) -> bool:
        return bool(self.worker and self.worker.connected)

    def get_idn(self) -> str:
        return self.state.get("idn", "")

    def update_ui(self):
        connected = self.state["connected"]
        if connected != self._last_connected:
            self._last_connected = connected
            if self.on_connection_change:
                try:
                    self.on_connection_change(self.alias, connected)
                except Exception:
                    pass

        if connected:
            self.status_lbl.configure(text="已连接", foreground="green")
            self.conn_btn.configure(text="断开")
            self.idn_lbl.configure(text=f"IDN: {self.state.get('idn', '')}")
            reading = self.state.get("reading")
            if reading:
                parts = [f"{k}={v:.4e}" if isinstance(v, float) else f"{k}={v}"
                         for k, v in reading.items()]
                self.read_lbl.configure(text="读数: " + ", ".join(parts))
            else:
                self.read_lbl.configure(text="读数: --")
        else:
            self.status_lbl.configure(text="未连接", foreground="gray")
            self.conn_btn.configure(text="连接")
            self.idn_lbl.configure(text="IDN: --")
            self.read_lbl.configure(text="读数: --")

        err = self.state.get("error", "")
        if err:
            self.status_lbl.configure(text=f"错误: {err[:30]}", foreground="red")


class ConnectionPanel(tk.Frame):
    """仪器连接面板：根据例程声明的仪器动态生成卡片。"""

    def __init__(self, parent, msg_queue: queue.Queue,
                 on_connection_change: Optional[Callable[[str, bool], None]] = None):
        super().__init__(parent, bg=COLOR_BG)
        self.msg_queue = msg_queue
        self.on_connection_change = on_connection_change
        self.cards: Dict[str, _InstrumentCard] = {}
        self._setup_ui()

    def _setup_ui(self):
        hdr = tk.Frame(self, bg=COLOR_BG)
        hdr.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(hdr, text="仪器连接", style="Title.TLabel").pack(anchor=tk.W)

        self.cards_frame = tk.Frame(self, bg=COLOR_BG)
        self.cards_frame.pack(fill=tk.X, expand=True)

    def set_instruments(self, instruments_meta: Dict[str, Dict[str, Any]]):
        """根据例程的 INSTRUMENTS 声明重新生成连接卡片。"""
        # 停止并移除旧卡片
        for card in self.cards.values():
            card.stop_worker()
            card.destroy()
        self.cards.clear()

        for alias, info in instruments_meta.items():
            inst_type = info.get("type", alias)
            meta = InstrumentRegistry.get(inst_type)
            if meta is None:
                self.msg_queue.put(("log", {"text": f"未知仪器类型: {inst_type}", "level": "error"}))
                continue
            card = _InstrumentCard(
                self.cards_frame, alias, meta, self.msg_queue,
                on_connection_change=self.on_connection_change,
            )
            card.pack(fill=tk.X, pady=(0, 8))
            self.cards[alias] = card

    def update_ui(self):
        for card in self.cards.values():
            card.update_ui()

    def set_enabled(self, enabled: bool):
        for card in self.cards.values():
            card.set_enabled(enabled)

    def get_connected_instruments(self) -> Dict[str, Any]:
        """返回已连接仪器实例字典。"""
        return {alias: card.get_instance() for alias, card in self.cards.items()
                if card.is_connected()}

    def get_instruments_idn(self) -> Dict[str, str]:
        return {alias: card.get_idn() for alias, card in self.cards.items()
                if card.is_connected()}

    def disconnect_all(self):
        for card in self.cards.values():
            card.disconnect()

    def stop_all_workers(self):
        for card in self.cards.values():
            card.stop_worker()
