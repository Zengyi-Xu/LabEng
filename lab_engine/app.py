"""Lab Engine 主应用。"""
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, Optional

from lab_engine.core.data_manager import DataManager
from lab_engine.core.param_store import ParamStore
from lab_engine.core.registry import RoutineMeta, RoutineRegistry
from lab_engine.core.routine_context import RoutineContext
from lab_engine.core.setup_graph import SetupGraph
from lab_engine.core.system_registry import SystemRegistry
from lab_engine.gui.connection_panel import ConnectionPanel
from lab_engine.gui.log_panel import LogPanel
from lab_engine.gui.plot_panel import PlotPanel
from lab_engine.gui.routine_panel import RoutinePanel
from lab_engine.gui.setup_panel import SetupPanel
from lab_engine.gui.shell import (
    COLOR_BG,
    COLOR_CARD,
    configure_styles,
    dpi_scale,
    make_card,
    set_dpi_aware,
    set_tk_scaling,
    setup_plot_fonts,
    UI_FONT,
)

# 确保本仓库的 ivlab 可用
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 触发仪器注册
import lab_engine.instruments  # noqa: F401


UPDATE_MS = 100


class _RoutineWorker(threading.Thread):
    """在后台线程中执行例程。"""

    def __init__(
        self,
        routine: RoutineMeta,
        instruments: Dict[str, Any],
        params: Dict[str, Any],
        context: RoutineContext,
    ):
        super().__init__(daemon=True)
        self.routine = routine
        self.instruments = instruments
        self.params = params
        self.context = context
        self.success = False
        self.error: Optional[str] = None

    def run(self):
        try:
            self.routine.run(self.instruments, self.params, self.context)
            self.success = True
        except Exception as exc:
            self.error = str(exc)
            self.context.error(f"例程异常: {exc}")
            self.success = False
        finally:
            self.context.done(success=self.success)


class LabEngineApp(tk.Tk):
    """Lab Engine 主窗口。"""

    def __init__(self):
        super().__init__()
        set_dpi_aware()
        self.scale = set_tk_scaling(self)
        setup_plot_fonts()

        self.title("Lab Engine — 通用实验室仪器控制引擎")
        self.configure(bg=COLOR_BG)

        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = min(int(sw * 0.85), dpi_scale(1500, self.scale))
        h = min(int(sh * 0.85), dpi_scale(950, self.scale))
        self.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        self.minsize(dpi_scale(1050, self.scale), dpi_scale(680, self.scale))

        configure_styles(self, self.scale)

        # 核心对象
        from lab_engine.paths import data_dir, draft_path, param_store_path, routines_dir, systems_dir
        self.registry = RoutineRegistry()
        self.registry.discover([routines_dir()])
        # 测试系统注册表：.py 例程（单位系统）+ .labsetup.json（组合系统）
        self.system_registry = SystemRegistry(self.registry)
        self.system_registry.discover([systems_dir(), data_dir()])
        self.data_manager = DataManager(data_dir())
        self.param_store = ParamStore(param_store_path())
        self.msg_queue: queue.Queue = queue.Queue()

        # 运行状态
        self.worker: Optional[_RoutineWorker] = None
        self.stop_event = threading.Event()
        self.current_context: Optional[RoutineContext] = None
        self._last_params: Dict[str, Any] = {}

        # 当前已应用的 Setup 项目（用于向运行页传递面板配置等）
        self.current_setup_graph: Optional[SetupGraph] = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(UPDATE_MS, self._poll_messages)
        self._draft_path = draft_path()
        self._notify_draft_if_any()
        self.after(60_000, self._autosave_draft)

    _DRAFT_INTERVAL_MS = 60_000

    def _autosave_draft(self):
        """每分钟把设计 Tab 的框图草稿存到 data/draft_setup.json。"""
        try:
            panel = getattr(self, "edit_setup_panel", None)
            if panel is not None and getattr(panel, "_has_project", False):
                self._draft_path.parent.mkdir(parents=True, exist_ok=True)
                panel.graph.save(self._draft_path)
        except Exception:
            pass
        self.after(self._DRAFT_INTERVAL_MS, self._autosave_draft)

    def _notify_draft_if_any(self):
        """启动时若存在上次未保存的草稿，提示用户可在设计 Tab「打开」恢复。"""
        if self._draft_path.exists():
            try:
                self.log_panel.append(
                    f"检测到上次的设计草稿（{self._draft_path}），"
                    "可在「测试系统设计」Tab 点「打开」恢复。")
            except Exception:
                pass

    def _build_ui(self):
        # 顶部标题栏
        header = tk.Frame(self, bg=COLOR_BG)
        header.pack(fill=tk.X, padx=16, pady=(14, 6))
        ttk.Label(header, text="Lab Engine", style="Title.TLabel").pack(side=tk.LEFT)
        self.status_lbl = ttk.Label(header, text="就绪")
        self.status_lbl.pack(side=tk.RIGHT)

        # 主区域：Tab 分页
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 8))
        self.notebook = notebook

        # Tab 1：运行测试系统
        run_tab = tk.Frame(notebook, bg=COLOR_BG)
        notebook.add(run_tab, text="  运行测试系统  ")
        self._build_run_tab(run_tab)

        # Tab 2：测试系统结构（只读，显示当前选中的测试系统）
        view_tab = tk.Frame(notebook, bg=COLOR_BG)
        notebook.add(view_tab, text="  测试系统结构  ")
        self._build_view_setup_tab(view_tab)

        # Tab 3：测试系统设计（可编辑，用于新建/编辑测试系统）
        edit_tab = tk.Frame(notebook, bg=COLOR_BG)
        notebook.add(edit_tab, text="  测试系统设计  ")
        self._build_edit_setup_tab(edit_tab)

        # RoutinePanel 初始化时会自动选择第一个测试系统，此时 view_setup_panel
        # 尚未创建，因此在这里手动同步一次当前系统到结构面板。
        current = getattr(self.routine_panel, "current_routine", None)
        system = getattr(self.routine_panel, "current_system", None)
        setup_graph = system.graph if (system is not None and system.is_setup) else None
        if current is not None:
            self.view_setup_panel.set_current_routine(current, setup_graph=setup_graph)
            try:
                idx = self.notebook.index(self.view_setup_panel.master)
                title = system.name if system is not None else current.name
                self.notebook.tab(idx, text=f"  测试系统结构: {title}  ")
            except Exception:
                pass
        else:
            self.view_setup_panel.set_current_routine(None)

    def _build_run_tab(self, parent):
        """构建原来的运行主界面。"""
        # 主区域：左侧可滚动面板 + 右侧图/日志
        main_paned = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True)

        # 先创建右侧面板，使 plot_panel / log_panel 在例程触发 on_select 前已存在
        right = tk.Frame(main_paned, bg=COLOR_BG)

        # 绘图区
        plot_card = make_card(right, fill=tk.BOTH, expand=True, pady=(0, 8))
        self.plot_panel = PlotPanel(plot_card)
        self.plot_panel.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # 日志区
        log_card = make_card(right, fill=tk.BOTH, expand=True)
        log_inner = tk.Frame(log_card, bg=COLOR_CARD)
        log_inner.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)
        ttk.Label(log_inner, text="运行日志", style="Section.TLabel").pack(anchor=tk.W)
        self.log_panel = LogPanel(log_inner, height=10)
        self.log_panel.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        # 左侧可滚动面板
        left_frame = tk.Frame(main_paned, bg=COLOR_BG)
        left_canvas = tk.Canvas(left_frame, bg=COLOR_BG, highlightthickness=0)
        left_vsb = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_vsb.set)
        left_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        left_inner = tk.Frame(left_canvas, bg=COLOR_BG)
        left_canvas.create_window((0, 0), window=left_inner, anchor="nw",
                                  width=dpi_scale(480, self.scale))
        left_inner.bind("<Configure>",
                        lambda _e: left_canvas.configure(scrollregion=left_canvas.bbox("all")))

        # 输出目录
        out_card = make_card(left_inner, fill=tk.X, pady=(0, 8))
        out_inner = tk.Frame(out_card, bg=COLOR_CARD)
        out_inner.pack(fill=tk.X, padx=12, pady=10)
        ttk.Label(out_inner, text="输出目录:", style="Section.TLabel").pack(side=tk.LEFT)
        self.output_dir_var = tk.StringVar(value=str(self.data_manager.base_dir))
        ttk.Entry(out_inner, textvariable=self.output_dir_var, width=28).pack(side=tk.LEFT, padx=8)
        ttk.Button(out_inner, text="浏览", command=self._browse_output_dir).pack(side=tk.LEFT)

        # CodePlot 绘图工作台
        from lab_engine.gui.codeplot_panel import open_codeplot_window
        ttk.Button(left_inner, text="📈 CodePlot 绘图工作台",
                   command=lambda: open_codeplot_window(self)).pack(fill=tk.X, pady=(0, 8))

        # 仪器连接面板
        self.connection_panel = ConnectionPanel(left_inner, self.msg_queue)
        self.connection_panel.pack(fill=tk.X, pady=(0, 8))

        # 测试系统面板（创建时会触发 on_select，依赖 plot_panel 已存在）
        self.routine_panel = RoutinePanel(
            left_inner,
            self.registry,
            on_select=self._on_routine_selected,
            on_run=self._on_run,
            on_stop=self._on_stop,
            param_store=self.param_store,
            system_registry=self.system_registry,
        )
        self.routine_panel.pack(fill=tk.X, pady=(0, 8))

        main_paned.add(left_frame, weight=1)
        main_paned.add(right, weight=2)

    def _build_view_setup_tab(self, parent):
        """构建“例程结构”只读查看页面。"""
        self.view_setup_panel = SetupPanel(
            parent,
            routine_registry=self.registry,
            scale=self.scale,
            viewer_mode=True,
            on_edit_request=self._on_edit_routine_request,
        )
        self.view_setup_panel.pack(fill=tk.BOTH, expand=True)

    def _build_edit_setup_tab(self, parent):
        """构建“测试系统设计”可编辑页面。"""
        self.edit_setup_panel = SetupPanel(
            parent,
            routine_registry=self.registry,
            scale=self.scale,
            on_apply=self._on_setup_apply,
            on_routines_changed=self._on_routines_changed,
        )
        self.edit_setup_panel.pack(fill=tk.BOTH, expand=True)

    def _on_routines_changed(self):
        """例程/系统文件有新增/变更时刷新运行 Tab 的下拉列表。"""
        if getattr(self, "system_registry", None) is not None:
            self.system_registry.refresh()
        if getattr(self, "routine_panel", None) is not None:
            self.routine_panel._refresh_routine_list(keep_selection=True)

    def _on_edit_routine_request(self, routine):
        """从“例程结构”只读页请求编辑：跳到设计 Tab 并载入该例程为模板。"""
        if routine is None:
            return
        try:
            idx = self.notebook.index(self.edit_setup_panel.master)
            self.notebook.select(idx)
        except Exception:
            pass
        self.edit_setup_panel.load_routine_as_template(routine)

    def _on_setup_apply(self, graph: SetupGraph):
        """Setup 框图点击"应用到运行配置"时保存当前项目，并尝试同步到运行页。"""
        self.current_setup_graph = graph
        self.log_panel.append("测试系统设计已应用")

        # 如果运行页当前已选中某个例程，立即按 Setup 项目里的面板配置刷新参数表单
        routine = getattr(self.routine_panel, "current_routine", None)
        if routine is not None:
            panel_cfg = self._find_setup_panel_for_routine(routine.name)
            if panel_cfg is not None:
                self.routine_panel.set_panel(panel_cfg)

    def _find_setup_panel_for_routine(self, routine_name: str) -> Optional[Dict[str, Any]]:
        """在当前 Setup 项目中查找引用指定例程的 routine 节点，返回其 panel_cfg。"""
        if self.current_setup_graph is None:
            return None
        for node in self.current_setup_graph.nodes.values():
            if node.node_type != "routine":
                continue
            ref = node.data.get("template") or node.data.get("routine_name") or ""
            if ref == routine_name:
                return node.data.get("panel_cfg")
        return None

    def _browse_output_dir(self):
        path = filedialog.askdirectory(title="选择输出目录", initialdir=self.output_dir_var.get())
        if path:
            self.output_dir_var.set(path)
            self.data_manager = DataManager(Path(path))

    def _on_routine_selected(self, routine: Optional[RoutineMeta]):
        # RoutinePanel 初始化时会触发一次 on_select，此时 self.routine_panel 尚未赋值
        routine_panel = getattr(self, "routine_panel", None)
        system = getattr(routine_panel, "current_system", None) if routine_panel is not None else None
        self.plot_panel.clear()
        self.log_panel.clear()
        if routine:
            self.connection_panel.set_instruments(routine.instruments)
            system_label = system.name if system is not None else routine.name
            self.log_panel.append(f"已加载测试系统: {system_label}")
        else:
            self.connection_panel.set_instruments({})

        # 同步当前系统到“测试系统结构”只读查看面板，并更新 Tab 标题
        if hasattr(self, "view_setup_panel") and self.view_setup_panel is not None:
            setup_graph = None
            if system is not None and system.is_setup:
                setup_graph = system.graph
            elif self.current_setup_graph is not None:
                setup_graph = self.current_setup_graph
            self.view_setup_panel.set_current_routine(routine, setup_graph=setup_graph)
            if system is not None:
                tab_text = f"  测试系统结构: {system.name}  "
            elif routine:
                tab_text = f"  测试系统结构: {routine.name}  "
            else:
                tab_text = "  测试系统结构  "
            try:
                idx = self.notebook.index(self.view_setup_panel.master)
                self.notebook.tab(idx, text=tab_text)
            except Exception:
                pass

    def _on_run(self):
        routine = self.routine_panel.current_routine
        if routine is None:
            messagebox.showwarning("提示", "请先选择一个例程")
            return

        instruments = self.connection_panel.get_connected_instruments()
        missing = [
            alias for alias, info in routine.instruments.items()
            if info.get("required", True) and alias not in instruments
        ]
        if missing:
            messagebox.showwarning("仪器未连接",
                                   f"请先连接以下必需仪器: {', '.join(missing)}")
            return

        params = self.routine_panel.get_params()
        self._last_params = params
        self.stop_event.clear()
        self.routine_panel.set_running(True)
        self.connection_panel.set_enabled(False)
        self.routine_panel.reset_progress()
        self.plot_panel.clear()

        # 创建本次运行目录
        run_id, run_dir = self.data_manager.new_run(routine.name)
        self.current_context = RoutineContext(
            run_id=run_id,
            output_dir=run_dir,
            msg_queue=self.msg_queue,
            stop_event=self.stop_event,
        )

        self.log_panel.append(f"开始运行: {routine.name} ({run_id})")
        self.status_lbl.configure(text=f"运行中: {routine.name}")

        self.worker = _RoutineWorker(
            routine=routine,
            instruments=instruments,
            params=params,
            context=self.current_context,
        )
        self.worker.start()

    def _on_stop(self):
        self.stop_event.set()
        self.log_panel.append("已请求停止例程", level="warn")
        self.status_lbl.configure(text="停止请求已发送")

    def _poll_messages(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                self._handle_message(msg)
        except queue.Empty:
            pass

        self.connection_panel.update_ui()
        self.after(UPDATE_MS, self._poll_messages)

    def _handle_message(self, msg: tuple):
        kind, payload = msg
        if kind == "log":
            self.log_panel.append(payload.get("text", ""), payload.get("level", "info"))
        elif kind == "progress":
            self.routine_panel.set_progress(payload.get("current", 0), payload.get("total", 1))
        elif kind == "point":
            self.plot_panel.add_point(**payload)
        elif kind == "data":
            self.plot_panel.add_points(self.current_context.points if self.current_context else [])
        elif kind == "done":
            self._on_routine_done(payload)

    def _on_routine_done(self, payload: Dict[str, Any]):
        self.routine_panel.set_running(False)
        self.connection_panel.set_enabled(True)
        success = payload.get("success", False)

        if self.current_context and self.worker:
            routine = self.routine_panel.current_routine
            points = self.current_context.points
            run_dir = self.current_context.output_dir
            if points:
                self.data_manager.save_csv(run_dir, points)
            self.data_manager.save_metadata(
                run_dir=run_dir,
                routine_name=routine.name if routine else "unknown",
                routine_path=routine.path if routine else Path(),
                params=self._last_params,
                instruments=self.connection_panel.get_instruments_idn(),
            )
            self.log_panel.append(f"数据已保存: {run_dir}")

        if success:
            self.status_lbl.configure(text="运行完成")
            self.log_panel.append("例程运行完成")
        else:
            error = self.worker.error if self.worker else None
            self.status_lbl.configure(text="运行失败" + (f": {error}" if error else ""))
            self.log_panel.append("例程运行结束（未成功）", level="warn")

        self.worker = None
        self.current_context = None

    def _on_close(self):
        # 关闭前最后一次保存设计草稿
        try:
            panel = getattr(self, "edit_setup_panel", None)
            if panel is not None and getattr(panel, "_has_project", False):
                self._draft_path.parent.mkdir(parents=True, exist_ok=True)
                panel.graph.save(self._draft_path)
        except Exception:
            pass
        self.stop_event.set()
        self.connection_panel.disconnect_all()
        self.connection_panel.stop_all_workers()
        if self.worker and self.worker.is_alive():
            self.worker.join(timeout=2.0)
        self.destroy()


def main():
    app = LabEngineApp()
    app.mainloop()


if __name__ == "__main__":
    main()
