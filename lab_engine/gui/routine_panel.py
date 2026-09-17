"""例程选择、参数渲染、运行控制面板。"""
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable, Dict, List, Optional

from lab_engine.core.registry import RoutineMeta, RoutineRegistry
from lab_engine.core.param_store import ParamStore
from lab_engine.core.system_registry import SystemMeta, SystemRegistry, SystemTask
from lab_engine.gui.shell import COLOR_BG, COLOR_CARD, COLOR_TEXT_DIM, UI_FONT


class RoutinePanel(ttk.Frame):
    """例程选择与参数面板。"""

    def __init__(
        self,
        parent,
        registry: RoutineRegistry,
        on_select: Optional[Callable[[Optional[RoutineMeta]], None]] = None,
        on_run: Optional[Callable[[], None]] = None,
        on_stop: Optional[Callable[[], None]] = None,
        param_store: Optional[ParamStore] = None,
        system_registry: Optional[SystemRegistry] = None,
    ):
        super().__init__(parent)
        self.registry = registry
        self.system_registry = system_registry
        self.on_select = on_select
        self.on_run = on_run
        self.on_stop = on_stop
        self.param_store = param_store
        self.current_routine: Optional[RoutineMeta] = None
        self.current_system: Optional[SystemMeta] = None
        self.current_task: Optional[SystemTask] = None
        self.param_vars: Dict[str, tk.Variable] = {}
        self.param_widgets: List[tk.Widget] = []
        self._loading = False  # 批量回填参数时抑制自动保存
        self._active_panel: Optional[Dict[str, Any]] = None  # Setup 项目传入的面板配置
        self._setup_ui()
        self._refresh_routine_list()

    def _setup_ui(self):
        # 标题
        hdr = tk.Frame(self, bg=COLOR_BG)
        hdr.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(hdr, text="测试系统", style="Title.TLabel").pack(anchor=tk.W)

        # 系统选择
        sel_frame = tk.Frame(self, bg=COLOR_CARD)
        sel_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(sel_frame, text="选择测试系统:", style="Section.TLabel").pack(
            anchor=tk.W, padx=12, pady=(10, 4)
        )
        self.routine_var = tk.StringVar()
        combo_row = tk.Frame(sel_frame, bg=COLOR_CARD)
        combo_row.pack(fill=tk.X, padx=12, pady=(0, 4))
        self.routine_combo = ttk.Combobox(
            combo_row,
            textvariable=self.routine_var,
            state="readonly",
            values=[],
            font=(UI_FONT, 10),
        )
        self.routine_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.routine_combo.bind("<<ComboboxSelected>>", self._on_routine_selected)
        ttk.Button(combo_row, text="🔄 刷新", command=self._on_refresh, width=6).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        # 组合系统（.labsetup.json）的测量任务二级选择
        self.task_row = tk.Frame(sel_frame, bg=COLOR_CARD)
        self.task_var = tk.StringVar()
        ttk.Label(self.task_row, text="测量任务:", style="Section.TLabel").pack(
            side=tk.LEFT, padx=(12, 4)
        )
        self.task_combo = ttk.Combobox(
            self.task_row,
            textvariable=self.task_var,
            state="readonly",
            values=[],
            width=24,
            font=(UI_FONT, 10),
        )
        self.task_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 12))
        self.task_combo.bind("<<ComboboxSelected>>", self._on_task_selected)

        self.desc_lbl = ttk.Label(sel_frame, text="", wraplength=400,
                                  style="DimCard.TLabel")
        self.desc_lbl.pack(anchor=tk.W, padx=12, pady=(0, 10))

        # 参数区
        self.params_frame = tk.Frame(self, bg=COLOR_CARD)
        self.params_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(self.params_frame, text="参数", style="Section.TLabel").pack(
            anchor=tk.W, padx=12, pady=(10, 4)
        )
        self.params_inner = tk.Frame(self.params_frame, bg=COLOR_CARD)
        self.params_inner.pack(fill=tk.X, padx=12, pady=(0, 10))

        # 控制按钮
        ctrl = tk.Frame(self, bg=COLOR_CARD)
        ctrl.pack(fill=tk.X, pady=(0, 8))
        self.run_btn = ttk.Button(ctrl, text="▶ 开始测试", style="Accent.TButton",
                                  command=self._on_run_click, state=tk.DISABLED)
        self.run_btn.pack(side=tk.LEFT, padx=(12, 8), pady=12)
        self.stop_btn = ttk.Button(ctrl, text="■ 停止", command=self._on_stop_click,
                                   state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 12), pady=12)

        # 进度条
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress = ttk.Progressbar(self, variable=self.progress_var,
                                        maximum=100.0)
        self.progress.pack(fill=tk.X, pady=(0, 8))

    def _refresh_routine_list(self, keep_selection: bool = False):
        names = self.system_registry.names() if self.system_registry else self.registry.names()
        self.routine_combo["values"] = names
        current = self.routine_var.get()
        if keep_selection and current in names:
            self._load_system(current)
        elif names:
            self.routine_var.set(names[0])
            self._load_system(names[0])
        else:
            self.routine_var.set("")
            self._load_system("")

    def _on_refresh(self):
        """重新扫描例程/系统目录并刷新下拉框；有失败时弹出汇总。"""
        if self.system_registry is not None:
            self.system_registry.refresh()
        else:
            self.registry.refresh()
        self._refresh_routine_list(keep_selection=True)

        reports = []
        if self.system_registry is not None:
            reports.append(("系统", getattr(self.system_registry, "last_report", None)))
        else:
            reports.append(("例程", getattr(self.registry, "last_report", None)))
        lines: List[str] = []
        for label, report in reports:
            if not report:
                continue
            if report.get("failed") or report.get("duplicates"):
                lines.append(f"[{label}] 已加载 {len(report.get('loaded', []))} 个。")
                if report.get("duplicates"):
                    lines.append("  名称冲突（后者覆盖前者）：")
                    lines.extend(f"    • {d}" for d in report["duplicates"])
                if report.get("failed"):
                    lines.append("  加载失败：")
                    lines.extend(f"    • {f}" for f in report["failed"])
        if lines:
            messagebox.showwarning("扫描结果", "\n".join(lines))

    def _on_routine_selected(self, _event=None):
        name = self.routine_var.get()
        if name:
            self._load_system(name)

    def _load_system(self, name: str):
        """加载一个测试系统（.py 单位系统或 .labsetup.json 组合系统）。"""
        self.current_system = None
        self.current_task = None
        if self.system_registry is None:
            self._load_routine(name)
            return

        system = self.system_registry.get(name)
        self.current_system = system
        if system is None:
            self._load_routine("")
            return

        if not system.is_setup:
            # 单位系统：行为与原来选择单个例程一致
            self.task_row.pack_forget()
            self._load_routine(system.routine.name if system.routine else "")
            return

        # 组合系统：先选测量任务，再加载对应例程
        tasks = system.tasks()
        if not tasks:
            self.task_row.pack_forget()
            self.task_combo["values"] = []
            self.task_var.set("")
            self.current_routine = None
            self.desc_lbl.configure(text="此组合系统没有可用的测量任务节点")
            self._clear_params()
            self.run_btn.configure(state=tk.DISABLED)
            if self.on_select:
                self.on_select(None)
            return

        self.task_row.pack(fill=tk.X, pady=(0, 4), before=self.desc_lbl)
        labels = [t.label for t in tasks]
        self.task_combo["values"] = labels
        current = self.task_var.get()
        if current in labels:
            self._load_task(tasks[labels.index(current)])
        else:
            self.task_var.set(labels[0])
            self._load_task(tasks[0])

    def _on_task_selected(self, _event=None):
        system = self.current_system
        if system is None or not system.is_setup:
            return
        label = self.task_var.get()
        for task in system.tasks():
            if task.label == label:
                self._load_task(task)
                return

    def _load_task(self, task: SystemTask):
        """组合系统中选中某个测量任务后，加载其对应例程与面板配置。"""
        self.current_task = task
        routine = self.registry.get(task.routine_name)
        if routine is None:
            self.current_routine = None
            self.desc_lbl.configure(
                text=f"找不到测量任务对应的例程脚本：{task.routine_name}")
            self._clear_params()
            self.run_btn.configure(state=tk.DISABLED)
            if self.on_select:
                self.on_select(None)
            return
        self._load_routine(routine.name, panel=task.panel_cfg)

    def _load_routine(self, name: str, panel: Optional[Dict[str, Any]] = None):
        routine = self.registry.get(name)
        self.current_routine = routine
        if routine is None:
            self.desc_lbl.configure(text="")
            self._clear_params()
            self.run_btn.configure(state=tk.DISABLED)
            if self.on_select:
                self.on_select(None)
            return

        desc = routine.description or ""
        if routine.icon:
            desc = f"{routine.icon} {desc}"
        self.desc_lbl.configure(text=desc)
        saved = self.param_store.get(routine.name) if self.param_store else {}
        # 外部传入的 panel（来自 Setup 项目）优先于 .py 文件自带的 PANEL
        effective_panel = panel if panel is not None else getattr(routine, "panel", None)
        self._build_params(routine.params, saved, effective_panel)
        self.run_btn.configure(state=tk.NORMAL)
        if self.on_select:
            self.on_select(routine)

    def set_panel(self, panel: Optional[Dict[str, Any]]):
        """外部（如 app.py 从 Setup 项目）注入当前例程的面板配置。"""
        if self.current_routine is not None:
            self._load_routine(self.current_routine.name, panel=panel)
        else:
            self._active_panel = panel

    def _clear_params(self):
        for w in self.param_widgets:
            w.destroy()
        self.param_widgets.clear()
        self.param_vars.clear()

    def _build_params(self, params: List[Dict[str, Any]],
                      saved: Optional[Dict[str, Any]] = None,
                      panel: Optional[Dict[str, Any]] = None):
        self._clear_params()

        # 按 PANEL 描述调整参数顺序与可见性（所见即所得）
        if panel:
            hidden = set(panel.get("hidden_params", []))
            params = [p for p in params if p.get("name", "") not in hidden]
            order: Dict[str, int] = {}
            for sec in panel.get("sections", []):
                if sec.get("type") == "params":
                    for idx, pname in enumerate(sec.get("params", [])):
                        order.setdefault(pname, idx)
            if order:
                params = sorted(params,
                                key=lambda p: order.get(p.get("name", ""), len(order)))

        if not params:
            ttk.Label(self.params_inner, text="（此例程无参数）",
                      style="DimCard.TLabel").pack(anchor=tk.W)
            return

        self._loading = True
        try:
            for p in params:
                self._make_param_widget(p, saved or {})
        finally:
            self._loading = False

    def _autosave_param(self, name: str, var: tk.Variable):
        """单个参数被修改时自动写入参数存储。"""
        if self._loading or self.current_routine is None or self.param_store is None:
            return
        try:
            value = var.get()
        except Exception:
            return
        self.param_store.update(self.current_routine.name, name, value)

    def _save_all_params(self):
        """把当前所有参数值整体写入参数存储。"""
        if self.current_routine is None or self.param_store is None:
            return
        values: Dict[str, Any] = {}
        for name, var in self.param_vars.items():
            try:
                values[name] = var.get()
            except Exception:
                pass
        self.param_store.set(self.current_routine.name, values)

    def _make_param_widget(self, p: Dict[str, Any], saved: Dict[str, Any]):
        name = p["name"]
        label = p.get("label", name)
        ptype = p.get("type", "float")
        default = saved.get(name, p.get("default", 0))

        row = tk.Frame(self.params_inner, bg=COLOR_CARD)
        row.pack(fill=tk.X, pady=3)
        self.param_widgets.append(row)

        ttk.Label(row, text=f"{label}:", width=26).pack(side=tk.LEFT)

        if ptype == "bool":
            var = tk.BooleanVar(value=bool(default))
            cb = ttk.Checkbutton(row, variable=var, text="启用")
            cb.pack(side=tk.LEFT)
        elif ptype == "choice":
            var = tk.StringVar(value=str(default))
            choices = p.get("choices", [])
            combo = ttk.Combobox(row, textvariable=var, values=choices,
                                 state="readonly", width=16)
            combo.pack(side=tk.LEFT)
        elif ptype == "int":
            var = tk.IntVar(value=int(default))
            entry = ttk.Entry(row, textvariable=var, width=16)
            entry.pack(side=tk.LEFT)
        elif ptype == "float":
            var = tk.DoubleVar(value=float(default))
            entry = ttk.Entry(row, textvariable=var, width=16)
            entry.pack(side=tk.LEFT)
        else:
            var = tk.StringVar(value=str(default))
            entry = ttk.Entry(row, textvariable=var, width=24)
            entry.pack(side=tk.LEFT)

        self.param_vars[name] = var
        var.trace_add("write", lambda *_: self._autosave_param(name, var))
        if ptype == "choice":
            combo.bind("<<ComboboxSelected>>",
                       lambda _e: self._autosave_param(name, var))

    def get_params(self) -> Dict[str, Any]:
        """收集当前参数值。"""
        params = {}
        if self.current_routine is None:
            return params
        for p in self.current_routine.params:
            name = p["name"]
            var = self.param_vars.get(name)
            ptype = p.get("type", "float")
            if var is None:
                # 被 PANEL.hidden_params 隐藏的参数在 UI 中不渲染，
                # 但例程仍需要拿到值；此时使用 PARAMS 里的默认值。
                params[name] = p.get("default", 0)
                continue
            try:
                if ptype == "bool":
                    params[name] = bool(var.get())
                elif ptype == "int":
                    params[name] = int(var.get())
                elif ptype == "float":
                    params[name] = float(var.get())
                else:
                    params[name] = str(var.get())
            except Exception as exc:
                raise ValueError(f"参数 '{name}' 格式错误: {exc}")
        return params

    def validate_params(self) -> bool:
        """校验参数范围。"""
        if self.current_routine is None:
            messagebox.showwarning("未选择测试系统", "请先选择一个测试系统/测量任务")
            return False
        try:
            params = self.get_params()
        except ValueError as exc:
            messagebox.showerror("参数错误", str(exc))
            return False

        for p in self.current_routine.params:
            name = p["name"]
            value = params.get(name)
            if value is None:
                continue
            if "min" in p and value < p["min"]:
                messagebox.showerror("参数越界",
                                     f"{p.get('label', name)} 不能小于 {p['min']}")
                return False
            if "max" in p and value > p["max"]:
                messagebox.showerror("参数越界",
                                     f"{p.get('label', name)} 不能大于 {p['max']}")
                return False
        return True

    def select_routine(self, name: str):
        """外部调用：切换到指定例程。"""
        values = self.routine_combo["values"] or []
        if name not in values:
            return
        self.routine_var.set(name)
        self._load_routine(name)

    def set_running(self, running: bool):
        """设置运行状态按钮。"""
        if running:
            self.run_btn.configure(state=tk.DISABLED)
            self.stop_btn.configure(state=tk.NORMAL)
            self.routine_combo.configure(state=tk.DISABLED)
        else:
            self.run_btn.configure(state=tk.NORMAL)
            self.stop_btn.configure(state=tk.DISABLED)
            self.routine_combo.configure(state="readonly")

    def set_progress(self, current: float, total: float):
        """更新进度条。"""
        if total > 0:
            pct = min(100.0, max(0.0, current / total * 100.0))
        else:
            pct = 0.0
        self.progress_var.set(pct)

    def reset_progress(self):
        self.progress_var.set(0.0)

    def _on_run_click(self):
        if not self.validate_params():
            return
        self._save_all_params()
        if self.on_run:
            self.on_run()

    def _on_stop_click(self):
        if self.on_stop:
            self.on_stop()
