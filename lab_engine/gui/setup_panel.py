"""Lab Engine Setup 框图编辑器面板。

提供基于 tk.Canvas 的可视化节点编辑器：
- 工具栏添加 Host / Comm / Instrument / Routine 节点
- 拖拽移动节点
- 在端口之间连线（贝塞尔曲线）
- 画布缩放、平移、网格吸附
- 属性面板编辑节点参数
- 保存/加载 .labsetup.json
- 一键同步到 Run tab
"""
import copy
import math
import tkinter as tk
import uuid
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from lab_engine.core.registry import InstrumentRegistry, RoutineRegistry
from lab_engine.core.setup_graph import (
    NODE_HEIGHT,
    NODE_WIDTH,
    PORT_RADIUS,
    Node,
    Port,
    SetupGraph,
)
from lab_engine.gui.shell import (
    COLOR_BG,
    COLOR_CARD,
    COLOR_PRIMARY,
    COLOR_TEXT_DIM,
    UI_FONT,
    dpi_scale,
)


# 节点类型配色
NODE_COLORS = {
    "host": "#3B82F6",      # 蓝
    "comm": "#8B5CF6",      # 紫
    "instrument": "#10B981",  # 绿
    "routine": "#F59E0B",   # 橙
    # 代码可视化节点类型
    "core": "#164E63",      # 深青
    "gui": "#7C3AED",       # 紫
    "hardware": "#059669",  # 绿
    "nn": "#DB2777",        # 品红
    "plot": "#EA580C",      # 橙
    "scan": "#0891B2",      # 青
    "util": "#475569",      # 灰
    "class": "#8B5CF6",     # 紫
    "function": "#3B82F6",  # 蓝
    "method": "#06B6D4",    # 青
}

# 端口类型配色
PORT_COLORS = {
    "control": "#EF4444",   # 红
    "comm": "#EAB308",      # 黄
    "data": "#22C55E",      # 绿
    "any": "#64748B",       # 灰
}

GRID_SIZE = 20
GRID_COLOR = "#64748B"  # 深灰蓝色，在浅灰背景上更清晰

# 全局连线样式选项（key -> 显示名）
EDGE_STYLES = {
    "bezier": "贝塞尔曲线",
    "straight": "直线",
    "elbow": "直角肘形",
    "elbow_round": "圆弧肘形",
}


def _edge_points(x1: float, y1: float, x2: float, y2: float,
                 style: str) -> Tuple[List[float], bool]:
    """根据连线样式返回 canvas 坐标点列和 smooth 标志。"""
    cx = (x1 + x2) / 2
    if style == "straight":
        return [x1, y1, x2, y2], False
    if style == "elbow":
        return [x1, y1, cx, y1, cx, y2, x2, y2], False
    if style == "elbow_round":
        return [x1, y1, cx, y1, cx, y2, x2, y2], True
    # 默认贝塞尔曲线
    return [x1, y1, cx, y1, cx, y2, x2, y2], True


class SetupPanel(ttk.Frame):
    """Setup 框图编辑器。"""

    def __init__(
        self,
        parent,
        routine_registry: RoutineRegistry,
        on_apply: Optional[Callable[[SetupGraph], None]] = None,
        scale: Optional[float] = None,
        on_node_activate: Optional[Callable[[Node], None]] = None,
        node_activate_label: str = "查看详情",
        viewer_mode: bool = False,
        on_routines_changed: Optional[Callable[[], None]] = None,
        on_edit_request: Optional[Callable[[Any], None]] = None,
    ):
        super().__init__(parent)
        self.routine_registry = routine_registry
        self.on_apply = on_apply
        self.on_node_activate = on_node_activate
        self.node_activate_label = node_activate_label
        self.viewer_mode = viewer_mode
        self.on_routines_changed = on_routines_changed
        self.on_edit_request = on_edit_request
        if scale is None:
            from lab_engine.gui.shell import get_system_dpi
            scale = max(get_system_dpi() / 96.0, 1.0)
        self.scale = scale

        self.graph = SetupGraph()
        self.selected_node_id: Optional[str] = None
        self.selected_node_ids: Set[str] = set()  # 多选集合（框选 / Shift 点击）
        self._marquee_rect: Optional[int] = None
        self._marquee_start: Optional[Tuple[float, float]] = None
        self._clipboard: Optional[Dict[str, Any]] = None
        self._paste_count = 0
        self._drag_node_id: Optional[str] = None
        self._drag_node_start: Optional[Tuple[float, float]] = None
        self._drag_mouse_start: Optional[Tuple[float, float]] = None
        self._drag_start: Optional[Tuple[float, float]] = None
        self._edge_start: Optional[Tuple[str, str]] = None
        self._temp_edge_line: Optional[int] = None
        self._temp_edge_coords: Optional[Tuple[float, float, float, float]] = None
        self._move_preview_rect: Optional[int] = None

        # 小地图交互状态
        self._minimap_pressed = False
        self._minimap_drag_active = False
        self._minimap_press_mx: float = 0.0
        self._minimap_press_my: float = 0.0
        self._minimap_view_tl: Tuple[float, float] = (0.0, 0.0)
        self._minimap_view_size: Tuple[float, float] = (0.0, 0.0)
        self._minimap_press_in_view = False
        self._minimap_bounds: Tuple[float, float, float, float, float, float] = (0.0, 0.0, 1.0, 1.0, 1.0, 1.0)

        # 画布状态
        self.zoom = 1.0
        self.pan_start: Optional[Tuple[float, float]] = None
        self._space_pressed = False
        self._panning = False

        # canvas item 缓存
        self._node_items: Dict[str, Dict[str, Any]] = {}
        self._edge_items: Dict[str, int] = {}
        self._grid_items: List[int] = []

        self._prop_vars: Dict[str, tk.Variable] = {}
        self._prop_widgets: List[tk.Widget] = []

        # 编辑/只读模式状态
        self._editable = False
        self._current_routine: Optional[Any] = None
        self._toolbar: Optional[tk.Frame] = None
        self._footer: Optional[tk.Frame] = None
        self._edit_mode_buttons: List[tk.Widget] = []
        self._new_routine_btn: Optional[tk.Widget] = None
        self._template_routine_btn: Optional[tk.Widget] = None
        self._gen_routine_btn: Optional[tk.Widget] = None

        # 悬浮说明状态
        self._tooltip: Optional[tk.Toplevel] = None
        self._tooltip_after: Optional[str] = None
        self._tooltip_text: str = ""
        self._tooltip_pos: Tuple[int, int] = (0, 0)

        self._build_ui()
        self._bind_events()
        # 默认进入编辑模式（viewer_mode 下保持只读）
        self.set_editable(not self.viewer_mode)

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self):
        # 顶部工具栏（viewer_mode 下隐藏）
        if not self.viewer_mode:
            self._toolbar = tk.Frame(self, bg=COLOR_BG)
            self._toolbar.pack(fill=tk.X, pady=(0, 8))
            toolbar = self._toolbar

            ttk.Label(toolbar, text="Setup 框图", style="Title.TLabel").pack(side=tk.LEFT)

            add_btn = ttk.Button(toolbar, text="+ 上位机", command=lambda: self._add_node("host"))
            add_btn.pack(side=tk.LEFT, padx=(16, 4))
            self._edit_mode_buttons.append(add_btn)
            add_btn = ttk.Button(toolbar, text="+ 通信", command=lambda: self._add_node("comm"))
            add_btn.pack(side=tk.LEFT, padx=4)
            self._edit_mode_buttons.append(add_btn)
            add_btn = ttk.Button(toolbar, text="+ 仪器", command=lambda: self._add_node("instrument"))
            add_btn.pack(side=tk.LEFT, padx=4)
            self._edit_mode_buttons.append(add_btn)
            add_btn = ttk.Button(toolbar, text="+ 例程", command=lambda: self._add_node("routine"))
            add_btn.pack(side=tk.LEFT, padx=4)
            self._edit_mode_buttons.append(add_btn)

            ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
            ttk.Button(toolbar, text="清空", command=self._new_graph).pack(side=tk.LEFT, padx=4)
            ttk.Button(toolbar, text="打开", command=self._load_graph).pack(side=tk.LEFT, padx=4)
            ttk.Button(toolbar, text="保存", command=self._save_graph).pack(side=tk.LEFT, padx=4)

            ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
            self._new_routine_btn = ttk.Button(
                toolbar, text="✚ 新建例程", command=self._on_new_routine
            )
            self._new_routine_btn.pack(side=tk.LEFT, padx=4)
            self._template_routine_btn = ttk.Button(
                toolbar, text="📋 基于模板新建", command=self._on_new_from_template
            )
            self._template_routine_btn.pack(side=tk.LEFT, padx=4)
            self._gen_routine_btn = ttk.Button(
                toolbar, text="⬇ 生成例程代码", command=self._on_generate_routine,
                state=tk.DISABLED,
            )
            self._gen_routine_btn.pack(side=tk.LEFT, padx=4)

            ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
            ttk.Label(toolbar, text="连线样式:").pack(side=tk.LEFT)
            self.edge_style_var = tk.StringVar(value=EDGE_STYLES["bezier"])
            style_combo = ttk.Combobox(
                toolbar, textvariable=self.edge_style_var, state="readonly", width=10,
                values=list(EDGE_STYLES.values()),
            )
            style_combo.pack(side=tk.LEFT, padx=(4, 4))
            style_combo.bind("<<ComboboxSelected>>", self._on_edge_style_changed)

        else:
            # viewer_mode：只显示标题和一个“编辑”入口按钮
            self._toolbar = tk.Frame(self, bg=COLOR_BG)
            self._toolbar.pack(fill=tk.X, pady=(0, 8))
            toolbar = self._toolbar
            ttk.Label(toolbar, text="例程结构（只读）", style="Title.TLabel").pack(side=tk.LEFT)
            self._edit_in_design_btn = ttk.Button(
                toolbar, text="✎ 在设计模式中编辑", command=self._on_edit_in_design,
                state=tk.DISABLED,
            )
            self._edit_in_design_btn.pack(side=tk.RIGHT, padx=4)

        # 主区域：canvas + 属性面板
        body = tk.Frame(self, bg=COLOR_BG)
        body.pack(fill=tk.BOTH, expand=True)

        # Canvas 容器（带滚动条）
        canvas_frame = tk.Frame(body, bg=COLOR_BG)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(
            canvas_frame,
            bg=COLOR_BG,
            highlightthickness=1,
            highlightbackground="#CBD5E1",
            scrollregion=(0, 0, dpi_scale(4000, self.scale), dpi_scale(3000, self.scale)),
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tk_scaling = self.canvas.tk.call("tk", "scaling")

        vbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)
        hbar = ttk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.canvas.xview)
        hbar.pack(fill=tk.X)
        self.canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)

        # 网格背景
        self._draw_grid()

        # 画布帮助文本（无边框，随画布滚动）
        self._draw_help_text()

        # 小地图
        self._build_minimap()

        # 属性面板（可滚动）
        prop_card = tk.Frame(body, bg=COLOR_CARD,
                             highlightbackground="#E2E8F0", highlightthickness=1, bd=0)
        prop_card.pack(side=tk.RIGHT, fill=tk.Y, padx=(8, 0))
        prop_card.pack_propagate(False)
        prop_card.configure(width=dpi_scale(300, self.scale))

        prop_inner = tk.Frame(prop_card, bg=COLOR_CARD)
        prop_inner.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

        ttk.Label(prop_inner, text="属性", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 8))

        # 可滚动属性区域
        self.prop_canvas = tk.Canvas(
            prop_inner,
            bg=COLOR_CARD,
            highlightthickness=0,
            width=dpi_scale(260, self.scale),
        )
        prop_vsb = ttk.Scrollbar(prop_inner, orient=tk.VERTICAL, command=self.prop_canvas.yview)
        self.prop_canvas.configure(yscrollcommand=prop_vsb.set)
        prop_vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.prop_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.prop_frame = tk.Frame(self.prop_canvas, bg=COLOR_CARD)
        self.prop_canvas.create_window((0, 0), window=self.prop_frame, anchor="nw",
                                        width=dpi_scale(260, self.scale))
        self.prop_frame.bind(
            "<Configure>",
            lambda _e: self.prop_canvas.configure(scrollregion=self.prop_canvas.bbox("all"))
        )

        if not self.viewer_mode:
            ttk.Label(prop_inner, text="提示: 选中节点后编辑属性，拖拽端口连线。\n滚轮上下平移，Shift+滚轮左右平移，Ctrl+滚轮缩放，空格+左键/中键拖拽平移。",
                      wraplength=dpi_scale(260, self.scale), style="DimCard.TLabel").pack(
                side=tk.BOTTOM, anchor=tk.W, pady=(8, 0)
            )

        # 底部操作栏（viewer_mode 下隐藏）
        if not self.viewer_mode:
            self._footer = tk.Frame(self, bg=COLOR_BG)
            self._footer.pack(fill=tk.X, pady=(8, 0))
            footer = self._footer
            self.apply_btn = ttk.Button(
                footer, text="应用到运行配置", style="Accent.TButton", command=self._apply_to_run
            )
            self.apply_btn.pack(side=tk.RIGHT)
            self._edit_mode_buttons.append(self.apply_btn)
            self.status_lbl = ttk.Label(footer, text="就绪")
            self.status_lbl.pack(side=tk.LEFT)
        else:
            self.status_lbl = ttk.Label(self, text="")
            self.status_lbl.pack(side=tk.BOTTOM, anchor=tk.W)

    def set_editable(self, editable: bool):
        """切换编辑/只读模式。

        查看现有例程时设为 False：禁止添加/删除节点、禁止拖拽/连线、
        属性面板只读；点击"新建例程"后设为 True，允许编辑。
        """
        self._editable = editable

        # 启用/禁用编辑工具栏按钮
        state = tk.NORMAL if editable else tk.DISABLED
        for btn in self._edit_mode_buttons:
            btn.configure(state=state)

        # "生成例程代码" 按钮只有在编辑模式下且框图包含 routine 节点时才可用
        self._update_generate_button_state()

        # 只读模式下取消当前选中，刷新属性面板为只读信息
        if not editable:
            self._select_node(None)
        else:
            self._show_edit_hint()

        mode = "编辑模式" if editable else "只读模式"
        self._set_status(f"已切换为 {mode}")

    def _update_generate_button_state(self):
        """根据当前编辑状态和框图内容更新“生成例程代码”按钮可用性。"""
        if self._gen_routine_btn is None:
            return
        if not self._editable:
            self._gen_routine_btn.configure(state=tk.DISABLED)
            return
        has_routine = any(n.node_type == "routine" for n in self.graph.nodes.values())
        self._gen_routine_btn.configure(state=tk.NORMAL if has_routine else tk.DISABLED)

    def _current_edge_style_key(self) -> str:
        var = getattr(self, "edge_style_var", None)
        if var is None:
            return "bezier"
        for key, display in EDGE_STYLES.items():
            if display == var.get():
                return key
        return "bezier"

    def _on_edge_style_changed(self, _event=None):
        self._redraw_all_edges()
        self._set_status(f"连线样式: {self.edge_style_var.get()}")

    def _on_edit_in_design(self):
        """viewer_mode 下请求跳转到设计模式编辑当前例程。"""
        if self.on_edit_request and self._current_routine is not None:
            self.on_edit_request(self._current_routine)

    def load_routine_as_template(self, routine: Any):
        """把指定例程载入为可编辑模板（供 app 从“例程结构”Tab 调用）。"""
        self._current_routine = routine
        self._build_routine_view(routine, editable=True)

    def set_current_routine(self, routine: Optional[Any]):
        """外部调用：切换 Setup 框图中显示的例程结构。

        运行 Tab 选中某个例程时，会同步调用此方法，Setup 框图只显示
        该例程的仪器依赖链，并进入只读模式；未选择例程时显示空画布。
        """
        self._current_routine = routine
        self.graph = SetupGraph()
        self.selected_node_id = None
        self._clear_property_panel()

        if routine is None:
            self.set_editable(False)
            self._redraw_all()
            if getattr(self, "_edit_in_design_btn", None) is not None:
                self._edit_in_design_btn.configure(state=tk.DISABLED)
            self._set_status("请在“运行”Tab 选择一个例程，或点击“新建例程/基于模板新建”开始编辑")
            return

        self._build_routine_view(routine, editable=False)
        if getattr(self, "_edit_in_design_btn", None) is not None:
            self._edit_in_design_btn.configure(
                state=tk.NORMAL if self.on_edit_request else tk.DISABLED
            )

    def _build_routine_view(self, routine: Any, editable: bool = False):
        """生成单个例程的框图结构：上位机 → 通信接口 → 仪器(们) → 例程。"""
        # 总是从空图开始，避免叠加旧节点（set_current_routine 也调用本方法）
        self.graph = SetupGraph()
        self.selected_node_id = None
        self.selected_node_ids = set()
        start_x = 120
        start_y = 180
        col_comm = 220
        col_inst = 240
        col_inst_step = 220

        # 上位机
        host = self.graph.add_node("host", start_x, start_y, label="上位机")
        # 通信接口
        comm = self.graph.add_node("comm", start_x + col_comm, start_y, label="通信接口")
        self.graph.add_edge(host.node_id, "control", comm.node_id, "control")

        # 仪器节点
        inst_nodes: Dict[str, Node] = {}
        inst_x = start_x + col_comm + col_inst
        for alias, info in routine.instruments.items():
            inst_key = info.get("type", alias)
            meta = InstrumentRegistry.get(inst_key)
            label = meta.name if meta else inst_key
            inst = self.graph.add_node(
                "instrument", inst_x, start_y,
                label=label,
                data={"instrument_key": inst_key, "alias": alias},
            )
            self._rebuild_instrument_ports(inst)
            self.graph.add_edge(comm.node_id, "comm", inst.node_id, "comm")
            inst_nodes[alias] = inst
            inst_x += col_inst_step

        # 例程节点：保存模板引用，以便生成代码时复用 PARAMS 等结构
        routine_node = self.graph.add_node(
            "routine", inst_x, start_y,
            label=routine.name,
            data={
                "template": routine.name,
                "_template_routine": routine,
            },
        )
        self._rebuild_routine_ports(routine_node)
        for alias, inst in inst_nodes.items():
            self.graph.add_edge(inst.node_id, "data", routine_node.node_id, f"inst_{alias}")

        self.canvas.delete("help_text")
        self._redraw_all()
        self._center_canvas_on_logical(start_x + (inst_x - start_x) / 2, start_y)

        self.set_editable(editable)
        if editable:
            self._set_status(f"编辑模板: {routine.name}，可修改仪器/参数后生成新例程")
        else:
            self._show_routine_info(routine)
            self._set_status(f"只读预览: {routine.name}")

    def _show_routine_info(self, routine: Any):
        """在右侧属性面板显示当前例程的元数据（只读）。"""
        self._clear_property_panel()
        ttk.Label(self.prop_frame, text=routine.name,
                  style="Section.TLabel").pack(anchor=tk.W, pady=(0, 8))
        if routine.description:
            ttk.Label(self.prop_frame, text=f"描述: {routine.description}",
                      style="DimCard.TLabel", wraplength=dpi_scale(240, self.scale)).pack(
                anchor=tk.W, pady=(0, 6))
        if routine.icon:
            ttk.Label(self.prop_frame, text=f"图标: {routine.icon}",
                      style="DimCard.TLabel").pack(anchor=tk.W, pady=(0, 6))

        ttk.Label(self.prop_frame, text="所需仪器:", style="Section.TLabel").pack(
            anchor=tk.W, pady=(8, 4))
        for alias, info in routine.instruments.items():
            inst_type = info.get("type", alias)
            required = "必需" if info.get("required", True) else "可选"
            ttk.Label(self.prop_frame, text=f"  • {alias} ({inst_type}) — {required}",
                      style="DimCard.TLabel").pack(anchor=tk.W)

        if routine.params:
            ttk.Label(self.prop_frame, text="参数:", style="Section.TLabel").pack(
                anchor=tk.W, pady=(8, 4))
            for p in routine.params:
                name = p.get("name", "")
                label = p.get("label", name)
                default = p.get("default", "")
                ttk.Label(self.prop_frame, text=f"  • {label}: 默认值 {default}",
                          style="DimCard.TLabel").pack(anchor=tk.W)

    def _build_minimap(self):
        """右下角小地图。"""
        self.minimap = tk.Canvas(
            self.canvas,
            width=dpi_scale(160, self.scale),
            height=dpi_scale(120, self.scale),
            bg="#E2E8F0",
            highlightthickness=1,
            highlightbackground="#CBD5E1",
        )
        # 固定在 canvas 右下角，不随内容滚动
        self.minimap.place(relx=1.0, rely=1.0, anchor=tk.SE, x=-8, y=-8)
        self.minimap.bind("<ButtonPress-1>", self._on_minimap_press)
        self.minimap.bind("<B1-Motion>", self._on_minimap_drag)
        self.minimap.bind("<ButtonRelease-1>", self._on_minimap_release)

    def _draw_help_text(self):
        """在画布左上角绘制帮助文本，节点统一放在下方空白处避免重叠。"""
        help_lines = [
            "Setup 框图",
            "",
            "拖拽端口连线，左键拖拽空白处框选",
            "Shift+点击多选，Ctrl+C/V 复制粘贴",
            "滚轮平移画面  Shift+滚轮水平平移  Ctrl+滚轮缩放",
            "节点关系：上位机 → 通信 → 仪器 → 例程",
        ]
        # 左上角对齐，确保初始画面一定能看到
        x = self._to_screen_scalar(30)
        y = self._to_screen_scalar(30)
        line_h = self._to_screen_scalar(18)
        for i, line in enumerate(help_lines):
            if i == 0:
                font = self._font(10, bold=True)
                fill = COLOR_PRIMARY
            elif line == "":
                continue
            else:
                font = self._font(8)
                fill = COLOR_TEXT_DIM
            self.canvas.create_text(
                x, y + i * line_h,
                text=line, font=font, fill=fill,
                anchor=tk.NW,
                tags=("help_text",),
            )

    def _draw_grid(self):
        """绘制网格背景（随 zoom/scale 变化）。"""
        for item in self._grid_items:
            self.canvas.delete(item)
        self._grid_items.clear()

        step = self._to_screen_scalar(GRID_SIZE)
        width = self.canvas.winfo_screenwidth() * 2
        height = self.canvas.winfo_screenheight() * 2
        for x in range(0, int(width), max(1, int(step))):
            for y in range(0, int(height), max(1, int(step))):
                item = self.canvas.create_oval(
                    x - 1, y - 1, x + 1, y + 1,
                    fill=GRID_COLOR, outline="",
                )
                self._grid_items.append(item)
        self.canvas.tag_lower("grid")
        for item in self._grid_items:
            self.canvas.addtag_withtag("grid", item)

    def _bind_events(self):
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Double-Button-1>", self._on_canvas_double_click)
        self.canvas.bind("<ButtonPress-3>", self._on_canvas_right_click)
        self.canvas.bind("<ButtonPress-2>", self._on_middle_press)
        self.canvas.bind("<B2-Motion>", self._on_middle_drag)
        self.canvas.bind("<ButtonRelease-2>", self._on_middle_release)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        # 空格键只绑定到画布，避免在 Notebook 其他 Tab 中误触发（空格平移画布）
        self.canvas.bind("<KeyPress-space>", self._on_space_press)
        self.canvas.bind("<KeyRelease-space>", self._on_space_release)
        # Delete/BackSpace 用 bind_all，保证焦点不在画布时也能删除节点；
        # 实际删除操作在 _on_delete_key 里会检查 _editable
        self.bind_all("<Delete>", self._on_delete_key, add="+")
        self.bind_all("<BackSpace>", self._on_delete_key, add="+")
        # 复制/粘贴
        self.bind_all("<Control-c>", self._on_copy, add="+")
        self.bind_all("<Control-C>", self._on_copy, add="+")
        self.bind_all("<Control-v>", self._on_paste, add="+")
        self.bind_all("<Control-V>", self._on_paste, add="+")
        # 悬浮说明（按 tag 绑定，之后绘制的节点/连线自动生效）
        self.canvas.tag_bind("node", "<Enter>", self._on_node_enter)
        self.canvas.tag_bind("node", "<Leave>", self._on_item_leave)
        self.canvas.tag_bind("node", "<Motion>", self._on_item_motion)
        self.canvas.tag_bind("edge", "<Enter>", self._on_edge_enter)
        self.canvas.tag_bind("edge", "<Leave>", self._on_item_leave)
        self.canvas.tag_bind("edge", "<Motion>", self._on_item_motion)

    # ------------------------------------------------------------------
    # 悬浮说明
    # ------------------------------------------------------------------
    def _schedule_tooltip(self, text: str, event):
        self._cancel_tooltip()
        self._tooltip_text = text
        self._tooltip_pos = (event.x_root + 14, event.y_root + 10)
        self._tooltip_after = self.after(400, self._show_tooltip)

    def _cancel_tooltip(self):
        if self._tooltip_after is not None:
            try:
                self.after_cancel(self._tooltip_after)
            except Exception:
                pass
            self._tooltip_after = None
        self._hide_tooltip()

    def _hide_tooltip(self):
        if self._tooltip is not None:
            try:
                self._tooltip.destroy()
            except Exception:
                pass
            self._tooltip = None

    def _show_tooltip(self):
        self._tooltip_after = None
        text = getattr(self, "_tooltip_text", "")
        if not text:
            return
        win = tk.Toplevel(self)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        lbl = tk.Label(
            win, text=text, justify=tk.LEFT,
            bg="#1E293B", fg="#E2E8F0", relief=tk.SOLID, bd=1,
            font=(UI_FONT, 9), padx=8, pady=5, wraplength=280,
        )
        lbl.pack()
        x, y = self._tooltip_pos
        win.update_idletasks()
        win.geometry(f"+{x}+{y}")
        self._tooltip = win

    def _move_tooltip(self, event):
        if self._tooltip is not None:
            self._tooltip.geometry(f"+{event.x_root + 14}+{event.y_root + 10}")

    def _current_tag_owner(self, event, prefix: str) -> Optional[str]:
        """从当前悬停 item 的 tags 里取出 node:<id> / edge:<id>。"""
        item = self.canvas.find_withtag("current")
        if not item:
            return None
        for tag in self.canvas.gettags(item[0]):
            if tag.startswith(prefix):
                return tag.split(":", 1)[1]
        return None

    def _on_node_enter(self, event):
        node_id = self._current_tag_owner(event, "node:")
        node = self.graph.get_node(node_id) if node_id else None
        if node is None:
            return
        self._schedule_tooltip(self._describe_node(node), event)

    def _on_edge_enter(self, event):
        edge_id = self._current_tag_owner(event, "edge:")
        edge = self.graph.edges.get(edge_id) if edge_id else None
        if edge is None:
            return
        src = self.graph.get_node(edge.source_node)
        dst = self.graph.get_node(edge.target_node)
        if src is None or dst is None:
            return
        self._schedule_tooltip(
            f"{src.label}  →  {dst.label}\n({edge.source_port} → {edge.target_port})",
            event,
        )

    def _on_item_leave(self, _event):
        self._cancel_tooltip()

    def _on_item_motion(self, event):
        if self._tooltip is not None:
            self._move_tooltip(event)

    def _describe_node(self, node: Node) -> str:
        """根据节点类型组装悬浮说明文字。"""
        if node.node_type == "host":
            return "上位机\n运行 Lab Engine 的电脑，负责调度仪器与例程。"
        if node.node_type == "comm":
            protocol = node.data.get("protocol", "RS-232")
            address = node.data.get("address", "")
            return (f"通信接口（{protocol}）\n"
                    f"上位机与仪器之间的通信链路。\n地址: {address}")
        if node.node_type == "instrument":
            key = node.data.get("instrument_key", "")
            meta = InstrumentRegistry.get(key)
            alias = node.data.get("alias", "")
            name = meta.name if meta else key
            desc = meta.description if meta else ""
            text = f"{name}"
            if alias:
                text += f"（别名: {alias}）"
            if desc:
                text += f"\n{desc}"
            return text
        if node.node_type == "routine":
            template = node.data.get("template") or node.data.get("routine_name") or ""
            routine = self.routine_registry.get(template) if template else None
            if routine:
                text = f"{routine.icon} {routine.name}" if routine.icon else routine.name
                if routine.description:
                    text += f"\n{routine.description}"
                return text
            return (f"{node.label}\n新例程：设置仪器连线后点击“生成例程代码”。")
        return node.label

    # ------------------------------------------------------------------
    # 节点与图操作
    # ------------------------------------------------------------------
    def _add_node(self, node_type: str):
        # 在画布中心附近添加，避免总是重叠
        cx = self.canvas.canvasx(self.canvas.winfo_width() / 2)
        cy = self.canvas.canvasy(self.canvas.winfo_height() / 2)
        x, y = self._from_screen(cx, cy)
        x += (len(self.graph.nodes) % 5) * 40
        y += (len(self.graph.nodes) % 3) * 140
        node = self.graph.add_node(node_type, x, y)
        self._init_node_defaults(node)
        self._draw_node(node)
        self._select_node(node.node_id)
        self._set_status(f"添加节点: {node.label}")
        self._update_minimap()
        self._update_generate_button_state()

    def _init_node_defaults(self, node: Node):
        if node.node_type == "comm":
            node.data.setdefault("protocol", "RS-232")
            node.data.setdefault("address", "COM1")
            node.data.setdefault("port", 9600)
        elif node.node_type == "instrument":
            keys = InstrumentRegistry.keys()
            node.data.setdefault("instrument_key", keys[0] if keys else "keithley2400")
            node.data.setdefault("alias", f"inst_{len(self.graph.nodes)}")
            self._rebuild_instrument_ports(node)
        elif node.node_type == "routine":
            node.data.setdefault("template", "")
            self._rebuild_routine_ports(node)

    def _rebuild_instrument_ports(self, node: Node):
        from lab_engine.core.setup_graph import Port
        node.ports = [
            Port("comm", "通信", "input", "comm"),
            Port("data", "数据", "output", "data"),
        ]

    def _rebuild_routine_ports(self, node: Node):
        from lab_engine.core.setup_graph import Port
        template = node.data.get("template") or node.data.get("routine_name") or ""
        routine = self.routine_registry.get(template) if template else None
        ports = []
        if routine:
            for alias in routine.instruments.keys():
                ports.append(Port(f"inst_{alias}", alias, "input", "data"))
        else:
            ports.append(Port("inst_a", "仪器 A", "input", "data"))
        node.ports = ports

    def _remove_node(self, node_id: str):
        self.graph.remove_node(node_id)
        self._erase_node(node_id)
        for edge_id in list(self._edge_items.keys()):
            if edge_id not in self.graph.edges:
                self._erase_edge(edge_id)
        self.selected_node_ids.discard(node_id)
        if self.selected_node_id == node_id:
            self.selected_node_id = None
            self._select_node(None)
        self._redraw_all_edges()
        self._update_minimap()
        self._update_generate_button_state()

    def _remove_edge(self, edge_id: str):
        self.graph.remove_edge(edge_id)
        self._erase_edge(edge_id)
        self._update_minimap()

    # ------------------------------------------------------------------
    # Canvas 绘制
    # ------------------------------------------------------------------
    def _round_rect(self, x1, y1, x2, y2, r=8, **kwargs):
        """绘制圆角矩形。"""
        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]
        return self.canvas.create_polygon(points, smooth=True, **kwargs)

    def _node_size(self, node: Node) -> Tuple[float, float]:
        """计算节点逻辑尺寸（不随 DPI / zoom 缩放）。"""
        n_ports = max(2, len(node.ports))
        w = NODE_WIDTH
        h = max(NODE_HEIGHT, 50 + n_ports * 28)
        return w, h

    def _to_screen(self, x: float, y: float) -> Tuple[float, float]:
        """把数据坐标转换为屏幕坐标（考虑 DPI 与 zoom）。"""
        return x * self.zoom * self.scale, y * self.zoom * self.scale

    def _to_screen_scalar(self, v: float) -> float:
        return v * self.zoom * self.scale

    def _from_screen(self, x: float, y: float) -> Tuple[float, float]:
        """把屏幕坐标转换为数据坐标。"""
        return x / (self.zoom * self.scale), y / (self.zoom * self.scale)

    def _font(self, size: int, bold: bool = False):
        """返回随 zoom/scale 缩放的字体，使字体像素高度与节点方框保持比例。

        tk scaling 会额外放大字体，因此用 4/3 补偿默认 96 DPI 下的 tk scaling
        （96/72 = 4/3），保证 96 DPI、zoom=1 时字体大小与原来一致。
        """
        s = max(1, int(round(size * 4 / 3 * self.zoom * self.scale / self.tk_scaling)))
        if bold:
            return (UI_FONT, s, "bold")
        return (UI_FONT, s)

    def _draw_node(self, node: Node):
        self._erase_node(node.node_id)
        items: Dict[str, Any] = {"ports": {}, "labels": []}

        w, h = self._node_size(node)
        x, y = self._to_screen(node.x, node.y)
        zw, zh = self._to_screen_scalar(w), self._to_screen_scalar(h)
        r = self._to_screen_scalar(8)

        color = NODE_COLORS.get(node.node_type, COLOR_PRIMARY)

        # 节点主体
        rect = self._round_rect(
            x, y, x + zw, y + zh, r=r,
            fill=COLOR_CARD, outline="#CBD5E1", width=max(1, int(2 * self.zoom)),
            tags=(f"node:{node.node_id}", "node"),
        )
        items["rect"] = rect

        # 标题背景
        title_h = self._to_screen_scalar(24)
        title_rect = self._round_rect(
            x, y, x + zw, y + title_h, r=r,
            fill=color, outline="",
            tags=(f"node:{node.node_id}", "node_title_bg"),
        )
        items["title_bg"] = title_rect

        # 标题文字
        title_text = self.canvas.create_text(
            x + zw / 2, y + title_h / 2,
            text=node.label, fill="white",
            font=self._font(9, bold=True),
            tags=(f"node:{node.node_id}", "node_title"),
        )
        items["title"] = title_text

        # 类型标签
        type_text = self.canvas.create_text(
            x + zw / 2, y + zh - self._to_screen_scalar(10),
            text=node.node_type, fill=COLOR_TEXT_DIM,
            font=self._font(8),
            tags=(f"node:{node.node_id}", "node_type"),
        )
        items["type_label"] = type_text

        # 端口
        inputs = [p for p in node.ports if p.direction == "input"]
        outputs = [p for p in node.ports if p.direction == "output"]

        for port in inputs:
            px, py = self._port_position(node, port, h)
            px, py = self._to_screen(px, py)
            pr = self._to_screen_scalar(PORT_RADIUS)
            c = self.canvas.create_oval(
                px - pr, py - pr, px + pr, py + pr,
                fill=PORT_COLORS.get(port.data_type, "#64748B"),
                outline="white", width=max(1, int(2 * self.zoom)),
                tags=(f"port:{node.node_id}:{port.name}", "port"),
            )
            items["ports"][port.name] = c
            lbl = self.canvas.create_text(
                px + self._to_screen_scalar(10), py,
                text=port.label, fill=COLOR_TEXT_DIM,
                font=self._font(8),
                anchor=tk.W, tags=(f"port_label:{node.node_id}:{port.name}",),
            )
            items["labels"].append(lbl)

        for port in outputs:
            px, py = self._port_position(node, port, h)
            px, py = self._to_screen(px, py)
            pr = self._to_screen_scalar(PORT_RADIUS)
            c = self.canvas.create_oval(
                px - pr, py - pr, px + pr, py + pr,
                fill=PORT_COLORS.get(port.data_type, "#64748B"),
                outline="white", width=max(1, int(2 * self.zoom)),
                tags=(f"port:{node.node_id}:{port.name}", "port"),
            )
            items["ports"][port.name] = c
            lbl = self.canvas.create_text(
                px - self._to_screen_scalar(10), py,
                text=port.label, fill=COLOR_TEXT_DIM,
                font=self._font(8),
                anchor=tk.E, tags=(f"port_label:{node.node_id}:{port.name}",),
            )
            items["labels"].append(lbl)

        # 状态指示圆点
        status_map = self.graph.validate_status()
        status_info = status_map.get(node.node_id, {})
        status = status_info.get("status", "normal")
        if status != "normal":
            dot_r = max(3, int(4 * self.zoom))
            dot_x = x + zw - dot_r * 2
            dot_y = y + title_h + dot_r * 1.5
            dot_color = {
                "warning": "#EAB308",
                "error": "#EF4444",
                "synced": "#22C55E",
            }.get(status, "#64748B")
            dot = self.canvas.create_oval(
                dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r,
                fill=dot_color, outline="white", width=max(1, int(1.5 * self.zoom)),
                tags=(f"status:{node.node_id}", "status_dot"),
            )
            items["status_dot"] = dot
            msg = status_info.get("message", "")
            if msg:
                msg_text = self.canvas.create_text(
                    dot_x - dot_r - 4, dot_y,
                    text=msg, fill=dot_color,
                    font=self._font(7),
                    anchor=tk.E,
                    tags=(f"status_msg:{node.node_id}", "status_msg"),
                )
                items["status_msg"] = msg_text

        self._node_items[node.node_id] = items
        self._update_node_selection_look(node.node_id)

    def _port_position(self, node: Node, port: Any, node_h: Optional[float] = None) -> Tuple[float, float]:
        """返回端口的逻辑坐标（未乘以 zoom/scale）。"""
        w, default_h = self._node_size(node)
        h = node_h if node_h is not None else default_h
        inputs = [p for p in node.ports if p.direction == "input"]
        outputs = [p for p in node.ports if p.direction == "output"]

        if port.direction == "input":
            idx = inputs.index(port)
            n = len(inputs)
            y = node.y + 30 + (idx + 1) * ((h - 40) / max(n, 1))
            return node.x, y
        else:
            idx = outputs.index(port)
            n = len(outputs)
            y = node.y + 30 + (idx + 1) * ((h - 40) / max(n, 1))
            return node.x + w, y

    def _erase_node(self, node_id: str):
        items = self._node_items.pop(node_id, {})
        for key, val in items.items():
            if key == "ports":
                for c in val.values():
                    self.canvas.delete(c)
            elif key == "labels":
                for lbl in val:
                    self.canvas.delete(lbl)
            else:
                self.canvas.delete(val)

    def _draw_edge(self, edge_id: str):
        self._erase_edge(edge_id)
        edge = self.graph.edges.get(edge_id)
        if edge is None:
            return
        src = self.graph.get_node(edge.source_node)
        dst = self.graph.get_node(edge.target_node)
        if src is None or dst is None:
            return
        src_port = src.port(edge.source_port)
        dst_port = dst.port(edge.target_port)
        if src_port is None or dst_port is None:
            return
        x1, y1 = self._port_position(src, src_port)
        x2, y2 = self._port_position(dst, dst_port)
        x1, y1 = self._to_screen(x1, y1)
        x2, y2 = self._to_screen(x2, y2)

        # 按全局样式生成连线几何
        points, smooth = _edge_points(x1, y1, x2, y2, self._current_edge_style_key())
        color = PORT_COLORS.get(src_port.data_type, COLOR_PRIMARY)
        line = self.canvas.create_line(
            *points,
            fill=color, width=max(1, int(2 * self.zoom)),
            smooth=smooth, splinesteps=24,
            tags=(f"edge:{edge_id}", "edge"),
        )
        self._edge_items[edge_id] = line
        self.canvas.tag_lower(line, "node")

    def _erase_edge(self, edge_id: str):
        line = self._edge_items.pop(edge_id, None)
        if line is not None:
            self.canvas.delete(line)

    def _redraw_all_edges(self):
        for edge_id in list(self._edge_items.keys()):
            self._erase_edge(edge_id)
        for edge_id in self.graph.edges.keys():
            self._draw_edge(edge_id)

    def _redraw_node(self, node_id: str):
        node = self.graph.get_node(node_id)
        if node is None:
            return
        self._draw_node(node)
        self._redraw_all_edges()
        self._update_minimap()

    def _update_node_selection_look(self, node_id: str):
        items = self._node_items.get(node_id)
        if items is None:
            return
        rect = items.get("rect")
        if rect is None:
            return
        if node_id in self.selected_node_ids:
            color = NODE_COLORS.get(self.graph.get_node(node_id).node_type, COLOR_PRIMARY)
            self.canvas.itemconfigure(rect, outline=color)
            self.canvas.itemconfigure(rect, width=max(2, int(3 * self.zoom)))
        else:
            self.canvas.itemconfigure(rect, outline="#CBD5E1")
            self.canvas.itemconfigure(rect, width=max(1, int(2 * self.zoom)))

    def _update_minimap(self):
        """更新小地图：显示节点缩略图与当前视口。"""
        self.minimap.delete("all")
        if not self.graph.nodes:
            self.minimap.create_text(
                self.minimap.winfo_width() / 2 or 80,
                self.minimap.winfo_height() / 2 or 60,
                text="空", fill=COLOR_TEXT_DIM, font=(UI_FONT, 8),
            )
            return

        # 逻辑坐标范围
        xs = [n.x for n in self.graph.nodes.values()]
        ys = [n.y for n in self.graph.nodes.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        # 留一点边距
        margin = 40
        min_x -= margin
        max_x += margin + NODE_WIDTH
        min_y -= margin
        max_y += margin + NODE_HEIGHT
        span_x = max(max_x - min_x, 1)
        span_y = max(max_y - min_y, 1)

        w = self.minimap.winfo_width() or dpi_scale(160, self.scale)
        h = self.minimap.winfo_height() or dpi_scale(120, self.scale)
        self._minimap_bounds = (min_x, min_y, span_x, span_y, w, h)

        # 绘制节点
        for node in self.graph.nodes.values():
            nx = (node.x - min_x) / span_x * w
            ny = (node.y - min_y) / span_y * h
            nw = max(4, NODE_WIDTH / span_x * w)
            nh = max(3, NODE_HEIGHT / span_y * h)
            self.minimap.create_rectangle(
                nx, ny, nx + nw, ny + nh,
                fill=NODE_COLORS.get(node.node_type, COLOR_PRIMARY),
                outline="white",
            )

        # 绘制当前视口
        vx1 = self.canvas.canvasx(0)
        vy1 = self.canvas.canvasy(0)
        vx2 = self.canvas.canvasx(self.canvas.winfo_width())
        vy2 = self.canvas.canvasy(self.canvas.winfo_height())
        # 转换为逻辑坐标
        lx1, ly1 = self._from_screen(vx1, vy1)
        lx2, ly2 = self._from_screen(vx2, vy2)
        # 映射到小地图
        mx1 = (lx1 - min_x) / span_x * w
        my1 = (ly1 - min_y) / span_y * h
        mx2 = (lx2 - min_x) / span_x * w
        my2 = (ly2 - min_y) / span_y * h
        self.minimap.create_rectangle(
            mx1, my1, mx2, my2,
            outline=COLOR_PRIMARY, width=2, dash=(3, 3),
        )

    def _get_view_logical_rect(self) -> Tuple[float, float, float, float]:
        """返回主画布当前视口的逻辑坐标范围 (x1, y1, x2, y2)。"""
        vx1 = self.canvas.canvasx(0)
        vy1 = self.canvas.canvasy(0)
        vx2 = self.canvas.canvasx(self.canvas.winfo_width())
        vy2 = self.canvas.canvasy(self.canvas.winfo_height())
        lx1, ly1 = self._from_screen(vx1, vy1)
        lx2, ly2 = self._from_screen(vx2, vy2)
        return lx1, ly1, lx2, ly2

    def _set_view_top_left_logical(self, lx: float, ly: float):
        """让主画布以指定逻辑坐标为左上角显示，并限制在滚动范围内。"""
        sr = self.canvas.cget("scrollregion")
        if not sr:
            return
        sr_w, sr_h = [float(v) for v in sr.split()[2:]]
        view_w = max(1, self.canvas.winfo_width())
        view_h = max(1, self.canvas.winfo_height())

        sx = lx * self.zoom * self.scale
        sy = ly * self.zoom * self.scale

        # 限制左上角不超出滚动区域
        sx = max(0.0, sx)
        sy = max(0.0, sy)
        sx = min(sx, max(0.0, sr_w - view_w))
        sy = min(sy, max(0.0, sr_h - view_h))

        self.canvas.xview_moveto(sx / sr_w)
        self.canvas.yview_moveto(sy / sr_h)
        self._update_minimap()

    def _center_canvas_on_logical(self, lx: float, ly: float):
        """让主画布以指定逻辑坐标为中心显示。"""
        view_w = max(1, self.canvas.winfo_width())
        view_h = max(1, self.canvas.winfo_height())
        tl_x = lx - self._from_screen(view_w / 2, 0)[0]
        tl_y = ly - self._from_screen(0, view_h / 2)[1]
        self._set_view_top_left_logical(tl_x, tl_y)

    def _on_minimap_press(self, event):
        if not self.graph.nodes:
            return
        self._update_minimap()
        self._minimap_pressed = True
        self._minimap_drag_active = False
        self._minimap_press_mx = event.x
        self._minimap_press_my = event.y

        min_x, min_y, span_x, span_y, w, h = self._minimap_bounds
        if w <= 0 or h <= 0:
            return

        # 当前视口逻辑范围
        lx1, ly1, lx2, ly2 = self._get_view_logical_rect()
        self._minimap_view_tl = (lx1, ly1)
        self._minimap_view_size = (lx2 - lx1, ly2 - ly1)

        # 鼠标按下位置对应的逻辑坐标
        mlx = min_x + event.x / w * span_x
        mly = min_y + event.y / h * span_y
        self._minimap_press_in_view = (lx1 <= mlx <= lx2 and ly1 <= mly <= ly2)
        self.minimap.config(cursor="fleur")

    def _on_minimap_drag(self, event):
        if not self._minimap_pressed:
            return
        min_x, min_y, span_x, span_y, w, h = self._minimap_bounds
        if w <= 0 or h <= 0:
            return

        dmx = event.x - self._minimap_press_mx
        dmy = event.y - self._minimap_press_my

        # 移动超过阈值才视为拖拽，避免轻微抖动触发拖拽
        if not self._minimap_drag_active:
            if math.hypot(dmx, dmy) < 3:
                return
            self._minimap_drag_active = True

        tl_x, tl_y = self._minimap_view_tl
        if self._minimap_press_in_view:
            # 抓住视口内部拖动：视口随鼠标偏移
            dx_logic = dmx / w * span_x
            dy_logic = dmy / h * span_y
            self._set_view_top_left_logical(tl_x + dx_logic, tl_y + dy_logic)
        else:
            # 在视口外拖动：鼠标当前位置作为视口中心
            mlx = min_x + event.x / w * span_x
            mly = min_y + event.y / h * span_y
            view_w, view_h = self._minimap_view_size
            self._set_view_top_left_logical(mlx - view_w / 2, mly - view_h / 2)

    def _on_minimap_release(self, event):
        if not self._minimap_pressed:
            return

        # 如果没有触发过拖拽，视为单击：跳转到点击位置
        if not self._minimap_drag_active:
            min_x, min_y, span_x, span_y, w, h = self._minimap_bounds
            if w > 0 and h > 0:
                mlx = min_x + event.x / w * span_x
                mly = min_y + event.y / h * span_y
                self._center_canvas_on_logical(mlx, mly)

        self._minimap_pressed = False
        self._minimap_drag_active = False
        self.minimap.config(cursor="")

    # ------------------------------------------------------------------
    # 鼠标交互
    # ------------------------------------------------------------------
    def _hit_test(self, x: float, y: float):
        """返回命中的对象信息（x, y 为逻辑坐标）。"""
        sx, sy = self._to_screen(x, y)
        r = max(2, int(3 * self.zoom * self.scale))
        items = self.canvas.find_overlapping(sx - r, sy - r, sx + r, sy + r)
        for item in reversed(items):
            tags = self.canvas.gettags(item)
            for tag in tags:
                if tag.startswith("port:"):
                    _, node_id, port_name = tag.split(":")
                    return "port", node_id, port_name
                if tag.startswith("node:"):
                    _, node_id = tag.split(":")
                    return "node", node_id, None
        return None, None, None

    def _canvas_to_graph(self, x: float, y: float) -> Tuple[float, float]:
        """把画布屏幕坐标转换为逻辑坐标。"""
        return self._from_screen(self.canvas.canvasx(x), self.canvas.canvasy(y))

    def _on_canvas_press(self, event):
        x, y = self._canvas_to_graph(event.x, event.y)
        kind, node_id, port_name = self._hit_test(x, y)

        if self._space_pressed:
            self._panning = True
            self.canvas.scan_mark(event.x, event.y)
            self.canvas.config(cursor="fleur")
            return

        if not self._editable:
            # 只读模式下只允许选中节点查看信息，禁止拖拽/连线
            if kind == "node":
                self._select_node(node_id)
            else:
                self._select_node(None)
            return

        if kind == "port":
            self._edge_start = (node_id, port_name)
            self._drag_start = (x, y)
            self._highlight_connectable_ports(node_id, port_name)
        elif kind == "node":
            if event.state & 0x0001:  # Shift：切换加选，不进入拖拽
                self._select_node(node_id, additive=True)
                return
            if node_id not in self.selected_node_ids:
                self._select_node(node_id)
            self._drag_node_id = node_id
            node = self.graph.get_node(node_id)
            if node:
                self._drag_node_start = (node.x, node.y)
            self._drag_mouse_start = (event.x, event.y)
            self._drag_start = (x, y)
        else:
            # 空白处：准备框选
            self._marquee_start = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))

    def _on_canvas_drag(self, event):
        x, y = self._canvas_to_graph(event.x, event.y)

        if self._panning:
            self.canvas.scan_dragto(event.x, event.y, gain=1)
            return

        if not self._editable:
            return

        if self._marquee_start is not None:
            self._draw_marquee(event)
        elif self._edge_start is not None:
            self._draw_temp_edge(x, y)
        elif self._drag_node_id is not None:
            node = self.graph.get_node(self._drag_node_id)
            if node and self._drag_node_start and self._drag_mouse_start:
                # 鼠标屏幕偏移量 -> 逻辑坐标偏移量
                dx_screen = event.x - self._drag_mouse_start[0]
                dy_screen = event.y - self._drag_mouse_start[1]
                dx = dx_screen / (self.zoom * self.scale)
                dy = dy_screen / (self.zoom * self.scale)

                new_x = self._drag_node_start[0] + dx
                new_y = self._drag_node_start[1] + dy

                # 网格吸附（逻辑坐标）
                new_x = round(new_x / GRID_SIZE) * GRID_SIZE
                new_y = round(new_y / GRID_SIZE) * GRID_SIZE

                # 更新节点位置
                node.x = new_x
                node.y = new_y
                self._redraw_node(self._drag_node_id)

                # 绘制高亮移动预览框
                self._draw_move_preview(node)

    def _on_canvas_release(self, event):
        x, y = self._canvas_to_graph(event.x, event.y)

        if self._panning:
            self._panning = False
            self.canvas.config(cursor="")
            return

        if not self._editable:
            return

        if self._marquee_start is not None:
            self._finish_marquee(event)
            return

        if self._edge_start is not None:
            self._clear_temp_edge()
            self._clear_port_highlights()
            kind, node_id, port_name = self._hit_test(x, y)
            if kind == "port" and node_id and port_name:
                src_id, src_port = self._edge_start
                edge = self.graph.add_edge(src_id, src_port, node_id, port_name)
                if edge:
                    self._draw_edge(edge.edge_id)
                    self._set_status("已创建连线")
                    self._update_minimap()
                else:
                    self._set_status("连线无效")
            self._edge_start = None
        elif self._drag_node_id is not None:
            self._drag_node_id = None
            self._drag_start = None
            self._drag_node_start = None
            self._drag_mouse_start = None
            self._clear_move_preview()

    def _on_canvas_double_click(self, event):
        """双击节点触发激活回调。"""
        if not self.on_node_activate:
            return
        x, y = self._canvas_to_graph(event.x, event.y)
        kind, node_id, _ = self._hit_test(x, y)
        if kind == "node":
            node = self.graph.get_node(node_id)
            if node:
                self.on_node_activate(node)

    def _on_canvas_right_click(self, event):
        """右键节点弹出上下文菜单。"""
        if not self.on_node_activate:
            return
        x, y = self._canvas_to_graph(event.x, event.y)
        kind, node_id, _ = self._hit_test(x, y)
        if kind != "node":
            return
        node = self.graph.get_node(node_id)
        if node is None:
            return
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label=self.node_activate_label,
            command=lambda: self.on_node_activate(node),
        )
        menu.post(event.x_root, event.y_root)

    def _on_middle_press(self, event):
        self._panning = True
        self.canvas.scan_mark(event.x, event.y)
        self.canvas.config(cursor="fleur")

    def _on_middle_drag(self, event):
        if self._panning:
            self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_middle_release(self, event):
        self._panning = False
        self.canvas.config(cursor="")

    def _on_mousewheel(self, event):
        if event.state & 0x0004:  # Ctrl
            factor = 1.1 if event.delta > 0 else 0.9
            old_zoom = self.zoom
            self.zoom *= factor
            self.zoom = max(0.3, min(3.0, self.zoom))
            if self.zoom != old_zoom:
                self._redraw_all()
                self._set_status(f"缩放: {self.zoom:.2f}x")
            return
        # 滚轮 = 上下平移，Shift+滚轮 = 左右平移
        steps = -3 if event.delta > 0 else 3
        if event.state & 0x0001:  # Shift
            self.canvas.xview_scroll(steps, "units")
        else:
            self.canvas.yview_scroll(steps, "units")

    def _on_space_press(self, _event):
        self._space_pressed = True

    def _on_space_release(self, _event):
        self._space_pressed = False
        self._panning = False
        self.pan_start = None
        self.canvas.config(cursor="")

    def _on_canvas_double(self, event):
        pass

    def _on_delete_key(self, _event):
        if not self._editable:
            return
        targets = list(self.selected_node_ids) or ([self.selected_node_id] if self.selected_node_id else [])
        if not targets:
            return
        for node_id in targets:
            self._remove_node(node_id)
        self._set_status(f"已删除 {len(targets)} 个节点")
        self._update_generate_button_state()

    # ------------------------------------------------------------------
    # 框选
    # ------------------------------------------------------------------
    def _draw_marquee(self, event):
        """更新框选矩形（屏幕/画布坐标）。"""
        x0, y0 = self._marquee_start
        x1, y1 = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        if self._marquee_rect is None:
            self._marquee_rect = self.canvas.create_rectangle(
                x0, y0, x1, y1,
                outline=COLOR_PRIMARY, width=2, dash=(4, 4),
                fill=COLOR_PRIMARY, stipple="gray25",
                tags=("marquee",),
            )
        else:
            self.canvas.coords(self._marquee_rect, x0, y0, x1, y1)

    def _finish_marquee(self, event):
        x0, y0 = self._marquee_start
        x1, y1 = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        additive = bool(event.state & 0x0001)  # Shift：加选
        self._marquee_start = None
        if self._marquee_rect is not None:
            self.canvas.delete(self._marquee_rect)
            self._marquee_rect = None
        # 拖动距离太小视为普通单击：清空选择
        if math.hypot(x1 - x0, y1 - y0) < 4:
            if not additive:
                self._select_node(None)
            return
        # 转换为逻辑坐标
        lx0, ly0 = self._from_screen(min(x0, x1), min(y0, y1))
        lx1, ly1 = self._from_screen(max(x0, x1), max(y0, y1))
        hit = []
        for node in self.graph.nodes.values():
            w, h = self._node_size(node)
            if node.x < lx1 and node.x + w > lx0 and node.y < ly1 and node.y + h > ly0:
                hit.append(node.node_id)
        if additive:
            for nid in hit:
                self.selected_node_ids.add(nid)
            if hit and self.selected_node_id is None:
                self.selected_node_id = hit[-1]
        else:
            self.selected_node_ids = set(hit)
            self.selected_node_id = hit[-1] if hit else None
        for nid in self.graph.nodes:
            self._update_node_selection_look(nid)
        if self.selected_node_id:
            self._build_property_panel()
        elif self._editable:
            self._show_edit_hint()
        else:
            self._show_empty_property_panel()

    # ------------------------------------------------------------------
    # 复制 / 粘贴
    # ------------------------------------------------------------------
    def _text_widget_focused(self) -> bool:
        """焦点在文本输入控件上时不响应画布快捷键。"""
        widget = self.focus_get()
        return isinstance(widget, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox, ttk.Spinbox))

    def _on_copy(self, _event=None):
        if not self._editable or self._text_widget_focused():
            return
        ids = set(self.selected_node_ids) or ({self.selected_node_id} if self.selected_node_id else set())
        ids = {nid for nid in ids if nid in self.graph.nodes}
        if not ids:
            return
        nodes = [copy.deepcopy(self.graph.nodes[nid].to_dict()) for nid in ids]
        edges = [
            copy.deepcopy(e.to_dict()) for e in self.graph.edges.values()
            if e.source_node in ids and e.target_node in ids
        ]
        self._clipboard = {"nodes": nodes, "edges": edges}
        self._paste_count = 0
        self._set_status(f"已复制 {len(nodes)} 个节点")

    def _on_paste(self, _event=None):
        if not self._editable or self._text_widget_focused():
            return
        if not self._clipboard or not self._clipboard["nodes"]:
            return
        self._paste_count += 1
        offset = GRID_SIZE * 2 * self._paste_count
        id_map: Dict[str, str] = {}
        new_ids: List[str] = []
        for nd in self._clipboard["nodes"]:
            new_id = f"n_{uuid.uuid4().hex[:8]}"
            id_map[nd["id"]] = new_id
            node = self.graph.add_node(
                nd["type"],
                nd.get("x", 100.0) + offset,
                nd.get("y", 100.0) + offset,
                label=nd.get("label", ""),
                data=copy.deepcopy(nd.get("data", {})),
                node_id=new_id,
            )
            node.ports = [
                Port.from_dict(pd) for pd in nd.get("ports", [])
            ] or node.ports
            self._draw_node(node)
            new_ids.append(new_id)
        for ed in self._clipboard["edges"]:
            self.graph.add_edge(
                id_map[ed["source_node"]], ed["source_port"],
                id_map[ed["target_node"]], ed["target_port"],
            )
        self._redraw_all_edges()
        self.selected_node_ids = set(new_ids)
        self.selected_node_id = new_ids[-1] if new_ids else None
        for nid in self.graph.nodes:
            self._update_node_selection_look(nid)
        if self.selected_node_id:
            self._build_property_panel()
        self._update_minimap()
        self._set_status(f"已粘贴 {len(new_ids)} 个节点")
        self._update_generate_button_state()

    def _select_node(self, node_id: Optional[str], additive: bool = False):
        """选中节点。additive=True 时（Shift 点击）切换加选/取消。"""
        if additive and node_id is not None:
            if node_id in self.selected_node_ids:
                self.selected_node_ids.discard(node_id)
                if self.selected_node_id == node_id:
                    self.selected_node_id = next(iter(self.selected_node_ids), None)
                self._update_node_selection_look(node_id)
                if self.selected_node_id:
                    self._build_property_panel()
                elif self._editable:
                    self._show_edit_hint()
                else:
                    self._show_empty_property_panel()
                return
            self.selected_node_ids.add(node_id)
            old = self.selected_node_id
            self.selected_node_id = node_id
            if old:
                self._update_node_selection_look(old)
            self._update_node_selection_look(node_id)
            self._build_property_panel()
            return

        old_ids = list(self.selected_node_ids)
        old_primary = self.selected_node_id
        self.selected_node_ids = {node_id} if node_id else set()
        self.selected_node_id = node_id
        for nid in set(old_ids) | self.selected_node_ids:
            if nid != old_primary and nid != node_id:
                self._update_node_selection_look(nid)
        if old_primary and old_primary != node_id:
            self._update_node_selection_look(old_primary)
        if node_id:
            self._update_node_selection_look(node_id)
            self._build_property_panel()
        elif self._editable:
            self._show_edit_hint()
        else:
            self._show_empty_property_panel()

    # ------------------------------------------------------------------
    # 临时连线
    # ------------------------------------------------------------------
    def _draw_move_preview(self, node: Node):
        """绘制节点移动预览框（亮蓝色虚线框）。"""
        self._clear_move_preview()
        w, h = self._node_size(node)
        x, y = self._to_screen(node.x, node.y)
        zw, zh = self._to_screen_scalar(w), self._to_screen_scalar(h)
        self._move_preview_rect = self.canvas.create_rectangle(
            x, y, x + zw, y + zh,
            outline="#3B82F6", width=2, dash=(4, 4),
            tags=("move_preview",),
        )
        self.canvas.tag_raise(self._move_preview_rect)

    def _clear_move_preview(self):
        if self._move_preview_rect is not None:
            self.canvas.delete(self._move_preview_rect)
            self._move_preview_rect = None

    def _draw_temp_edge(self, x2: float, y2: float):
        self._clear_temp_edge()
        src_id, src_port_name = self._edge_start
        src = self.graph.get_node(src_id)
        src_port = src.port(src_port_name) if src else None
        if src is None or src_port is None:
            return
        # 端口与鼠标都要走同一套坐标换算（zoom * scale），
        # 之前漏乘 scale 导致高 DPI 下临时线偏离光标、几乎看不见
        x1, y1 = self._port_position(src, src_port)
        x1, y1 = self._to_screen(x1, y1)
        x2, y2 = self._to_screen(x2, y2)
        points, smooth = _edge_points(x1, y1, x2, y2, self._current_edge_style_key())
        self._temp_edge_line = self.canvas.create_line(
            *points,
            fill=COLOR_PRIMARY, width=max(2, int(2 * self.zoom)),
            smooth=smooth, splinesteps=24,
            tags=("temp_edge",),
        )
        self.canvas.tag_raise(self._temp_edge_line)

    def _highlight_connectable_ports(self, source_node_id: str, source_port_name: str):
        """高亮可连接的端口。"""
        src_node = self.graph.get_node(source_node_id)
        src_port = src_node.port(source_port_name) if src_node else None
        if src_port is None:
            return

        for node_id, items in self._node_items.items():
            node = self.graph.get_node(node_id)
            if node is None:
                continue
            for port_name, item_id in items.get("ports", {}).items():
                port = node.port(port_name)
                if port is None:
                    continue
                # 可连接：方向相反，且类型匹配
                can_connect = (
                    port.direction != src_port.direction
                    and (port.data_type == src_port.data_type
                         or port.data_type == "any"
                         or src_port.data_type == "any")
                )
                if can_connect:
                    self.canvas.itemconfigure(item_id, outline="#22C55E")
                    self.canvas.itemconfigure(item_id, width=max(2, int(3 * self.zoom)))
                else:
                    self.canvas.itemconfigure(item_id, outline="#CBD5E1")
                    self.canvas.itemconfigure(item_id, width=max(1, int(1 * self.zoom)))

    def _clear_port_highlights(self):
        """清除端口高亮。"""
        for items in self._node_items.values():
            for item_id in items.get("ports", {}).values():
                self.canvas.itemconfigure(item_id, outline="white")
                self.canvas.itemconfigure(item_id, width=max(1, int(2 * self.zoom)))

    def _clear_temp_edge(self):
        if self._temp_edge_line is not None:
            self.canvas.delete(self._temp_edge_line)
            self._temp_edge_line = None
        self._clear_port_highlights()

    # ------------------------------------------------------------------
    # 画布重绘
    # ------------------------------------------------------------------
    def _redraw_all(self):
        """缩放或全量刷新。"""
        self.canvas.delete("all")
        self._node_items.clear()
        self._edge_items.clear()
        self._grid_items.clear()
        self._draw_grid()
        self._draw_help_text()
        for node in self.graph.nodes.values():
            self._draw_node(node)
        self._redraw_all_edges()
        self._update_minimap()

    # ------------------------------------------------------------------
    # 属性面板
    # ------------------------------------------------------------------
    def _clear_property_panel(self):
        for w in self.prop_frame.winfo_children():
            w.destroy()
        self._prop_widgets.clear()
        self._prop_vars.clear()

    def _show_empty_property_panel(self):
        self._clear_property_panel()
        ttk.Label(self.prop_frame, text="未选择节点", style="DimCard.TLabel").pack(
            anchor=tk.W, pady=(4, 0)
        )

    def _show_edit_hint(self):
        self._clear_property_panel()
        ttk.Label(self.prop_frame, text="编辑模式：添加节点并连线后，可生成例程代码",
                  style="DimCard.TLabel", wraplength=dpi_scale(240, self.scale)).pack(
            anchor=tk.W, pady=(4, 0))

    def _build_property_panel(self):
        self._clear_property_panel()
        node = self.graph.get_node(self.selected_node_id)
        if node is None:
            return

        # 通用：标签
        self._add_prop_entry(node, "label", "名称", node.label)

        if node.node_type == "comm":
            self._add_prop_choice(node, "protocol", "协议", ["RS-232", "GPIB", "TCPIP", "USBTMC", "VISA"])
            self._add_prop_entry(node, "address", "地址/端口", node.data.get("address", ""))
            self._add_prop_entry(node, "port", "参数", str(node.data.get("port", "")))

        elif node.node_type == "instrument":
            self._add_prop_choice(node, "instrument_key", "仪器类型", InstrumentRegistry.keys())
            self._add_prop_entry(node, "alias", "别名", node.data.get("alias", ""))
            meta = InstrumentRegistry.get(node.data.get("instrument_key", ""))
            if meta:
                for p in meta.connection_params:
                    name = p["name"]
                    label = p.get("label", name)
                    default = node.data.get(name, p.get("default", ""))
                    ptype = p.get("type", "")
                    if ptype == "choice":
                        self._add_prop_choice(node, name, label, p.get("choices", []))
                    else:
                        self._add_prop_entry(node, name, label, str(default))

        elif node.node_type == "routine":
            # 关联模板：决定节点有哪些仪器端口、可复用哪些 PARAMS
            names = self.routine_registry.names()
            template = node.data.get("template") or node.data.get("routine_name") or ""
            row = tk.Frame(self.prop_frame, bg=COLOR_CARD)
            row.pack(fill=tk.X, pady=3)
            ttk.Label(row, text="关联模板:", width=10).pack(side=tk.LEFT)
            tvar = tk.StringVar(value=template if template else "(无)")
            tcombo = ttk.Combobox(row, textvariable=tvar, state="readonly", width=18,
                                  values=["(无)"] + names)
            tcombo.pack(side=tk.LEFT, fill=tk.X, expand=True)
            tcombo.bind("<<ComboboxSelected>>",
                        lambda _e: self._on_template_changed(node, tvar))
            self._prop_vars["template"] = tvar
            self._prop_widgets.extend([row, tcombo])

            routine = self.routine_registry.get(template) if template else None
            if routine:
                for p in routine.params:
                    name = p["name"]
                    label = p.get("label", name)
                    default = node.data.get(name, p.get("default", ""))
                    ptype = p.get("type", "")
                    if ptype == "choice":
                        self._add_prop_choice(node, name, label, p.get("choices", []))
                    elif ptype == "bool":
                        self._add_prop_bool(node, name, label, bool(default))
                    else:
                        self._add_prop_entry(node, name, label, str(default))
            else:
                ttk.Label(self.prop_frame,
                          text="未关联模板：请在上方“名称”里填写新例程名，\n生成代码时会将其写入 NAME 字段。",
                          wraplength=dpi_scale(240, self.scale),
                          style="DimCard.TLabel").pack(anchor=tk.W, pady=(4, 0))

    def _add_prop_entry(self, node: Node, key: str, label: str, default: str):
        row = tk.Frame(self.prop_frame, bg=COLOR_CARD)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text=f"{label}:", width=10).pack(side=tk.LEFT)
        var = tk.StringVar(value=str(default))
        var.trace_add("write", lambda *_: self._on_prop_changed(node, key, var))
        entry = ttk.Entry(row, textvariable=var, width=20)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._prop_vars[key] = var
        self._prop_widgets.extend([row, entry])

    def _add_prop_choice(self, node: Node, key: str, label: str, values: List[str]):
        row = tk.Frame(self.prop_frame, bg=COLOR_CARD)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text=f"{label}:", width=10).pack(side=tk.LEFT)
        var = tk.StringVar(value=str(node.data.get(key, values[0] if values else "")))
        combo = ttk.Combobox(row, textvariable=var, values=values, state="readonly", width=18)
        combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._on_prop_changed(node, key, var))
        self._prop_vars[key] = var
        self._prop_widgets.extend([row, combo])

    def _add_prop_bool(self, node: Node, key: str, label: str, default: bool):
        row = tk.Frame(self.prop_frame, bg=COLOR_CARD)
        row.pack(fill=tk.X, pady=3)
        var = tk.BooleanVar(value=default)
        cb = ttk.Checkbutton(row, variable=var, text=label)
        cb.pack(side=tk.LEFT)
        var.trace_add("write", lambda *_: self._on_prop_changed(node, key, var))
        self._prop_vars[key] = var
        self._prop_widgets.extend([row, cb])

    def _on_prop_changed(self, node: Node, key: str, var: tk.Variable):
        if not self._editable:
            return
        value = var.get()
        old_value = node.data.get(key)
        node.data[key] = value

        if key == "label":
            node.label = value or _default_label(node.node_type)
            self._redraw_node(node.node_id)

        if key == "instrument_key":
            self._rebuild_instrument_ports(node)
            self._redraw_node(node.node_id)

        if key == "routine_name":
            self._rebuild_routine_ports(node)
            self._redraw_node(node.node_id)
            self._build_property_panel()

        self._set_status(f"更新 {node.label}.{key}")

    def _on_template_changed(self, node: Node, var: tk.Variable):
        """routine 节点切换关联模板。"""
        if not self._editable:
            return
        value = var.get()
        node.data["template"] = "" if value == "(无)" else value
        node.data.pop("routine_name", None)
        self._rebuild_routine_ports(node)
        self._redraw_node(node.node_id)
        self._build_property_panel()
        self._set_status(f"更新 {node.label}.模板 -> {node.data['template'] or '(无)'}")

    # ------------------------------------------------------------------
    # 例程生成
    # ------------------------------------------------------------------
    def _on_new_routine(self):
        """进入编辑模式，清空画布，提供最小例程模板。"""
        self._current_routine = None
        self.graph = SetupGraph()
        self.selected_node_id = None
        self._clear_property_panel()

        # 自动放置一个最小模板：上位机 → 通信 → 例程
        host = self.graph.add_node("host", 120, 180, label="上位机")
        comm = self.graph.add_node("comm", 340, 180, label="通信接口")
        routine = self.graph.add_node("routine", 780, 180, label="新例程", data={"template": ""})
        self._rebuild_routine_ports(routine)
        self.graph.add_edge(host.node_id, "control", comm.node_id, "control")

        self.canvas.delete("help_text")
        self._redraw_all()
        self.set_editable(True)
        self._update_generate_button_state()
        self._center_canvas_on_logical(450, 180)
        self._set_status("编辑模式：拖拽添加仪器节点并连线，完成后点击“生成例程代码”")

    def _on_new_from_template(self):
        """选择一个现有例程作为模板，进入编辑模式并加载其框图/参数。"""
        names = self.routine_registry.names()
        if not names:
            messagebox.showwarning("提示", "当前没有可用的例程模板")
            return

        # 简单弹窗选择模板
        dialog = tk.Toplevel(self)
        dialog.title("选择例程模板")
        dialog.configure(bg=COLOR_BG)
        dialog.transient(self)
        dialog.grab_set()

        ttk.Label(dialog, text="选择一个现有例程作为模板：", style="Subtitle.TLabel").pack(
            anchor=tk.W, padx=16, pady=(16, 8))

        listbox = tk.Listbox(dialog, height=min(10, len(names)), font=(UI_FONT, 10))
        for name in names:
            listbox.insert(tk.END, name)
        listbox.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)
        if names:
            listbox.selection_set(0)

        selected_name = [None]

        def on_ok():
            sel = listbox.curselection()
            if sel:
                selected_name[0] = names[sel[0]]
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btn_frame = tk.Frame(dialog, bg=COLOR_BG)
        btn_frame.pack(fill=tk.X, padx=16, pady=(0, 16))
        ttk.Button(btn_frame, text="确定", command=on_ok).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(btn_frame, text="取消", command=on_cancel).pack(side=tk.RIGHT)

        self.wait_window(dialog)

        if selected_name[0] is None:
            return

        routine = self.routine_registry.get(selected_name[0])
        if routine is None:
            return

        self._current_routine = routine
        self._build_routine_view(routine, editable=True)

    def _on_generate_routine(self):
        """根据当前框图生成一个例程 Python 文件骨架。"""
        if not self._editable:
            return

        routines = [n for n in self.graph.nodes.values() if n.node_type == "routine"]
        if not routines:
            messagebox.showwarning("提示", "框图中需要至少一个“例程”节点才能生成代码")
            return

        # 取第一个 routine 节点作为主体
        routine_node = routines[0]
        default_name = routine_node.label or routine_node.data.get("routine_name") or "新例程"
        routine_name = self._ask_new_routine_name(default_name)
        if routine_name is None:
            return

        # 同步节点显示名称，让用户在框图中也能看到最终命名
        routine_node.label = routine_name
        routine_node.data["routine_name"] = routine_name
        self._redraw_node(routine_node.node_id)

        # 收集仪器连接：通过边找到连到 routine 的 instrument 节点
        instruments: Dict[str, Dict[str, Any]] = {}
        for edge in self.graph.edges.values():
            if edge.target_node != routine_node.node_id:
                continue
            src_node = self.graph.get_node(edge.source_node)
            if src_node is None or src_node.node_type != "instrument":
                continue
            alias = src_node.data.get("alias") or f"inst_{len(instruments) + 1}"
            inst_key = src_node.data.get("instrument_key") or "keithley2400"
            instruments[alias] = {"type": inst_key, "required": True}

        # 收集参数：优先使用模板例程的 PARAMS 结构，并用属性面板中修改后的值覆盖
        template_routine = routine_node.data.get("_template_routine")
        if template_routine is None:
            template_key = routine_node.data.get("template") or routine_node.data.get("routine_name") or ""
            template_routine = self.routine_registry.get(template_key) if template_key else None
        params: List[Dict[str, Any]] = []
        if template_routine and template_routine.params:
            for p in template_routine.params:
                p = dict(p)
                name = p.get("name", "")
                if name and name in routine_node.data:
                    p["default"] = routine_node.data[name]
                params.append(p)

        # 生成文件名建议：用例程名转安全字符
        safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in routine_name).strip("_")
        if not safe_name:
            safe_name = "new_routine"
        default_path = (Path(__file__).resolve().parent.parent / "routines" / safe_name).with_suffix(".py")

        path = filedialog.asksaveasfilename(
            defaultextension=".py",
            filetypes=[("Python 例程", "*.py")],
            title="生成例程代码",
            initialfile=default_path.name,
            initialdir=str(default_path.parent),
        )
        if not path:
            return

        code = self._render_routine_template(routine_name, instruments, params)
        try:
            Path(path).write_text(code, encoding="utf-8")
            # 生成的新例程立即可选：刷新注册表并通知外部刷新下拉列表
            self.routine_registry.refresh()
            if self.on_routines_changed:
                self.on_routines_changed()
            self._set_status(f"已生成例程: {path}")
            messagebox.showinfo("生成成功", f"例程骨架已保存到:\n{path}\n\n请在 run() 函数中补充具体测试逻辑。")
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    def _ask_new_routine_name(self, default: str) -> Optional[str]:
        """弹出对话框让用户确认/修改新例程的显示名称（即文件内 NAME 字段）。"""
        dialog = tk.Toplevel(self)
        dialog.title("命名新例程")
        dialog.configure(bg=COLOR_BG)
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)

        ttk.Label(dialog, text="例程显示名称（写入文件内 NAME 字段）：",
                  style="Subtitle.TLabel").pack(anchor=tk.W, padx=16, pady=(16, 8))

        var = tk.StringVar(value=default)
        entry = ttk.Entry(dialog, textvariable=var, width=40)
        entry.pack(fill=tk.X, padx=16, pady=(0, 16))
        entry.select_range(0, tk.END)
        entry.icursor(tk.END)

        result: List[Optional[str]] = [None]

        def on_ok():
            name = var.get().strip()
            if not name:
                messagebox.showwarning("提示", "例程名称不能为空", parent=dialog)
                return
            if name in self.routine_registry.names():
                if not messagebox.askyesno(
                    "名称冲突",
                    f"已存在名为“{name}”的例程，继续保存会覆盖同名例程在 GUI 中的显示。\n仍要继续吗？",
                    parent=dialog,
                ):
                    return
            result[0] = name
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btn_frame = tk.Frame(dialog, bg=COLOR_BG)
        btn_frame.pack(fill=tk.X, padx=16, pady=(0, 16))
        ttk.Button(btn_frame, text="取消", command=on_cancel).pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="确定", command=on_ok, style="Accent.TButton").pack(
            side=tk.RIGHT, padx=(0, 8)
        )

        entry.bind("<Return>", lambda _e: on_ok())
        entry.bind("<Escape>", lambda _e: on_cancel())
        entry.focus_set()

        self.wait_window(dialog)
        return result[0]

    @staticmethod
    def _render_routine_template(
        name: str,
        instruments: Dict[str, Dict[str, Any]],
        params: List[Dict[str, Any]] = None,
    ) -> str:
        """渲染例程 Python 文件模板。"""
        inst_lines = ",\n".join(
            f'    "{alias}": {info}' for alias, info in instruments.items()
        )
        instrument_getters = "\n".join(
            f"    {alias} = instruments.get(\"{alias}\")" for alias in instruments.keys()
        )
        params = params or []
        params_repr = repr(params) if params else "[]"
        return f'''\
NAME = "{name}"
DESCRIPTION = ""
ICON = "🔬"

INSTRUMENTS = {{
{inst_lines}
}}

PARAMS = {params_repr}


def run(instruments, params, context):
    """执行例程。"""
    context.log("开始运行: {name}")
{instrument_getters}

    # TODO: 在这里补充具体的测试逻辑
    # 例如：
    # for v in np.linspace(params.get("start_v", 0), params.get("stop_v", 1), params.get("points", 11)):
    #     k2400.set_output_level(v)
    #     data = k2400.measure()
    #     context.point(voltage=v, current=data["current"])

    context.log("例程运行完成")
    context.done(success=True)
'''

    # ------------------------------------------------------------------
    # 文件操作
    # ------------------------------------------------------------------
    def get_graph(self) -> SetupGraph:
        return self.graph

    def set_graph(self, graph: SetupGraph):
        self.graph = graph
        self.selected_node_id = None
        self.zoom = 1.0
        self._redraw_all()
        self._select_node(None)
        self._set_status("已加载 Setup 图")
        self._update_generate_button_state()

    def _new_graph(self):
        self.set_graph(SetupGraph())
        self._set_status("新建空白 Setup 图")

    def _save_graph(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".labsetup.json",
            filetypes=[("Lab Setup", "*.labsetup.json"), ("JSON", "*.json")],
            title="保存 Setup 图",
        )
        if path:
            self.graph.save(Path(path))
            self._set_status(f"已保存: {path}")

    def _load_graph(self):
        path = filedialog.askopenfilename(
            filetypes=[("Lab Setup", "*.labsetup.json"), ("JSON", "*.json")],
            title="打开 Setup 图",
        )
        if path:
            try:
                graph = SetupGraph.load(Path(path))
                self.set_graph(graph)
                self._set_status(f"已打开: {path}")
            except Exception as exc:
                messagebox.showerror("打开失败", str(exc))

    def _apply_to_run(self):
        errors = self.graph.validate()
        if errors:
            messagebox.showwarning("Setup 图未通过校验", "\n".join(errors))
            return
        if self.on_apply:
            self.on_apply(self.graph)
            self._set_status("已同步到运行配置")

    def set_instrument_status(self, alias: str, connected: bool):
        """根据 Run tab 的仪器连接状态更新 Setup 框图节点。"""
        for node in self.graph.nodes_by_type("instrument"):
            node_alias = node.data.get("alias") or node.node_id
            if node_alias == alias:
                if connected:
                    self.graph.set_node_status_override(node.node_id, "synced", "已连接")
                else:
                    self.graph.set_node_status_override(node.node_id, "warning", "未连接")
                self._redraw_node(node.node_id)
                break

    def _set_status(self, text: str):
        self.status_lbl.configure(text=text)


def _default_label(node_type: str) -> str:
    from lab_engine.core.setup_graph import _default_label as dl
    return dl(node_type)
