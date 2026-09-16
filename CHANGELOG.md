# 更新日志

## 2026-09-17（LabEng 交接迭代）

项目正式定名 **LabEng** 并从 RS-232_lab_device 迁移为独立仓库
（`Zengyi-Xu/LabEng`）。以下两轮迭代以"毕业生交接"为目标：功能收敛 + 易用性 + 可扩展性 + AI 可协作。

### 迭代 2（交接打磨）

- **创建项目向导**：「🗂 新建项目」三步（创建方式 → 命名 → 勾选仪器）自动搭好
  上位机→通信→仪器→例程 框图与说明文本框。
- **合并保存**：移除「保存 Setup 图」，只留「💾 保存」；`SETUP_GRAPH`（框图快照）与
  `PANEL`（面板描述）以 Python 字面量嵌入例程 `.py`，重载时 1:1 还原布局与面板。
- **画布锁定**：设计 Tab 无项目时不可编辑，杜绝"画了图却生成不了"。
- **单一上位机**：向导自动创建；工具栏不再提供添加入口；粘贴防重。
- **多选整组拖动**：框选/Shift 多选后整组移动，网格吸附保持组内相对位置。
- **文本框（注释）节点**：「+ 文本」便签，属性面板多行编辑；画布固定帮助文字
  改为可删除的说明文本框。
- **例程操作面板（所见即所得）**：保存时自动生成 PANEL；设计页 routine 属性面板
  可编辑分区顺序/标题/参数显隐；运行页按 PANEL 渲染（顺序 + 显隐）。
- **例程加载结果汇总**：`RoutineRegistry.last_report` 记录成功/失败/重名，
  刷新时有失败弹窗汇总。
- **参数与草稿持久化**：参数改动自动存盘（已有）+ 设计框图每分钟/关闭时存草稿
  `data/draft_setup.json`，启动提示可恢复。
- **路径统一**（`lab_engine/paths.py`）：打包 exe 后数据/例程置于 exe 旁。
- **`build_exe.bat`**：PyInstaller 一键打包，`dist/` 内含 `routines/`。
- **文档**：重写 `README.md`；新增 `AGENTS.md`（AI 生成例程的完整约定）与
  `docs/TUTORIAL.md`（教材：开发史/架构/读码路线/动手实验）。
- 修复：嵌入 JSON 的 `true/false` 非法 Python（改 `repr()`）；`_add_prop_entry`
  误删；锁定态可编程加节点；打开旧 `.labsetup.json` 后仍锁定。

### 迭代 1（功能补全）

- 修复 `IV_2400.py` 不显示：与 `basic_iv_scan.py` 的 `NAME` 冲突，改名为
  「IV_2400 基础扫描」；registry 增加重复名警告。
- 例程下拉框增加「🔄 刷新」按钮（`RoutineRegistry.refresh()`）。
- 「生成例程代码」按钮状态随图内容实时更新（修灰显 bug）。
- 生成前弹出命名对话框（NAME 与文件名分离），冲突可确认覆盖。
- routine 属性面板拆分为「名称」+「关联模板」；未关联模板时给出指引。
- 生成成功后自动刷新例程列表。
- 例程注册表递归扫描子目录（`communication/` 下 3 个例程上线）。
- 参数持久化：`ParamStore`（`data/routine_params.json`），改参数即存、
  重选自动恢复、运行前整体落盘。
- 连线：修复拖拽临时线不可见（高 DPI 下坐标漏乘 scale）；工具栏新增全局
  连线样式选择（直线/直角肘形/圆弧肘形/贝塞尔）。
- 画布交互：滚轮上下平移、Shift+滚轮左右平移（Ctrl+滚轮缩放不变）。
- 悬浮说明：仪器/例程/连线悬停 tooltip（仪器注册表新增 description 字段）。
- 「例程结构」Tab 增加「✎ 在设计模式中编辑」入口。
- 修复 `_build_routine_view` 二次调用节点叠加。

### 迁移

- 新仓库 `Zengyi-Xu/LabEng`：迁移 `lab_engine/`、`ivlab/`、入口、依赖与文档；
  旧 RS-232 独立脚本、运行数据、截图、日志留在原仓库。
- 初始化 git 并推送 GitHub（main 分支）。

---

## 2026-09-16（迁移前，IVLab 阶段）



### 修复

- **Setup 框图编辑器交互修复**：修复“测试系统设计”页面节点无法拖拽、属性面板始终显示“未选择节点”的问题。
  - `SetupPanel` 初始化时默认进入编辑模式（非 viewer 模式），不再默认锁定为只读。
  - 拆分属性面板清空逻辑：`_clear_property_panel()` 仅清空控件；`_show_empty_property_panel()` / `_show_edit_hint()`
    分别负责无选中时的空状态提示；选中节点后不再残留“未选择节点”标签。

### 新增

- **Keithley 2400 Trigger Link 触发同步支持**：在 SCPI 层与 IV 扫描流程中完整封装 2400 后面板 Trigger Link（PS/2 口）触发功能。
  - `ivlab/instruments/scpi_mixin.py` 新增 `set_trigger_source`、`set_trigger_count`、
    `set_trigger_output`、`set_trigger_delay`、`init_measurement`、`fetch` 方法。
  - `ivlab/core/config.py` 的 `ScanConfig` 新增 `external_trigger`（从机等待触发）、
    `output_trigger`（主机输出触发）、`trigger_source`、`trigger_output`、`trigger_delay`、
    `external_trigger_timeout` 字段。
  - `ivlab/scanner/iv_scanner.py` 在 `setup_instrument()` 中根据配置下发触发命令：
    - 从机模式自动设为 `TRIG:SOUR TLIN` 并延长串口超时，扫描结束后恢复原始超时。
    - 主机模式自动设为 `TRIG:SOUR IMM` + `TRIG:OUTP SENS/SOUR/DEL`，可同步其他仪器。
    - 支持“中继/级联”模式：同时启用外部触发与输出触发时，2400 等待上游触发，测量完成后再输出脉冲到下游。
  - `lab_engine/routines/basic_iv_scan.py` 参数面板新增“使用外部触发”、“外部触发超时 (s)”、
    “输出触发同步其他设备”、“触发输出时机”四个选项。

### 新增

- **Lab Engine Setup 框图增强（Phase 2a/2b，解耦保留）**：重构可视化节点编辑器原型。
  - 节点改为圆角矩形，按类型配色（Host 蓝、Comm 紫、Instrument 绿、Routine 橙）。
  - 端口按数据类型配色（control 红、comm 黄、data 绿）。
  - 连线改为贝塞尔曲线，拖拽时实时预览。
  - 画布支持 `Ctrl+滚轮` 缩放、空格/中键拖拽平移、20px 网格吸附。
  - 属性面板改为可滚动区域。
  - 节点右上角显示状态圆点（warning/error），tooltip 显示原因。
  - 拖连线时高亮类型匹配的端口。
  - 右下角小地图显示节点分布。
  - 数据模型 `setup_graph.py` 新增 `validate_status()` 返回节点状态字典。
  - 仍保留保存/加载 `*.labsetup.json` 与“应用到运行配置”能力。

- **PlotPanel 多曲线增强**：支持按 `series` 字段分组绘制多条曲线，自动分配颜色与图例；数据点超过 5000 时自动抽稀。

- **Lab Engine 通信例程套件（Phase 3）**：把 DMT_PY_NN 的通信流程迁移为引擎例程。
  - `lab_engine/routines/communication/grid_scan.py`：偏置 × Vpp 二维网格扫描。
  - `lab_engine/routines/communication/dmt_pipeline.py`：QPSK 信道探测 → bitloading → 解调完整流程。
  - `lab_engine/routines/communication/nn_equalize.py`：ZY_BiGRU_GPU NN 后均衡。
  - 新增仪器适配器 `lab_engine/instruments/m8190a.py` 与 `lab_engine/instruments/oscilloscope.py`。
  - `lab_engine/instruments/__init__.py` 注册 `m8190a` 与 `oscilloscope`。

- **Lab Engine 例程扩展（Phase 2）**：把 `examples/` 中的多个脚本迁移为引擎内置例程。
  - `lab_engine/routines/basic_iv_scan.py`：Keithley 2400 基础 IV 扫描（single/double/sweep）。
  - `lab_engine/routines/hysteresis_scan.py`：双向回滞扫描 + 回滞面积/指数/对称因子分析。
  - `lab_engine/routines/mono_iv_scan.py`：CS260 扫波长 + K2400 固定电压读电流。
  - `lab_engine/routines/wavelength_scan.py`：Cornerstone 260 波长扫描。
  - `lab_engine/routines/sva1032x_vna.py`：Siglent SVA1032X VNA 模式 S11/S21 测量。
- **仪器注册扩展**：`lab_engine/instruments/__init__.py` 新增 `cornerstone260` 与 `sva1032x` 注册。

### 新增

- **Lab Engine Setup 框图（Phase 2，实验性，暂缓）**：新增可视化节点编辑器原型。
  - 节点类型：上位机（Host）、通信接口（Comm）、仪器（Instrument）、例程（Routine）。
  - 支持拖拽添加节点、鼠标连线、选中编辑属性、Delete 删除。
  - Setup 图可保存/加载为 `*.labsetup.json`。
  - 新增数据模型 `lab_engine/core/setup_graph.py` 与编辑器 `lab_engine/gui/setup_panel.py`。
  - 提供示例：`examples/setups/bias_iv_setup.labsetup.json`。
  - 由于节点关系与交互方式仍需进一步设计，**暂未挂载到主界面**，代码保留。

### 改进

- **RoutinePanel 新增 `select_routine`**：支持外部切换当前例程（为 Setup 同步预留）。

## 2026-09-16

### 新增

- **Lab Engine 通用仪器引擎（Phase 1）**：新增 `lab_engine/` 包与根目录启动入口
  `lab_engine_app.py`，提供可插例程的通用 GUI 外壳。
  - 自动发现 `lab_engine/routines/` 下的 `.py` 例程插件。
  - 按例程声明的 `INSTRUMENTS` 自动渲染仪器连接面板。
  - 按例程声明的 `PARAMS` 自动渲染参数面板（支持 float/int/choice/bool）。
  - 后台线程运行例程，实时显示日志、进度条和 I-V 曲线。
  - 每次运行自动生成 `data/<run_id>/data.csv` 与 `metadata.json`。
  - 内置首个例程 `lab_engine/routines/bias_iv_sweep.py`（GPD 偏置 + K2400 IV 扫描）。
- **GPD-4303S 驱动补全**：新增 `ivlab/instruments/gpd4303s.py`，使 `ivlab` 仪器包完整
  支持 GPD-4303S 四通道直流电源，为 Lab Engine 提供底层驱动。

### 改进

- **修复 `ivlab/instruments/__init__.py`**：移除对不存在模块的引用，使 `ivlab` 包可正常导入。
- **README / CHANGELOG 更新**：新增 Lab Engine 快速开始、例程插件接口规范与项目结构说明。

## 2026-09-14

### 新增

- **K2400 + GPD4303S 联合测试例程 GUI**：新增 `examples/k2400_gpd4303s_routine_gui.py`，
  在同一面板中连接并监控 Keithley 2400 源表与 GPD4303S 四通道电源，支持动态加载
  Python 插件例程、实时绘制 I-V 曲线、自动保存 CSV + JSON 元数据。
- **示例测试例程**：新增 `examples/routines/bias_iv_sweep.py`，演示 GPD CH1 提供直流
  偏置、K2400 执行电压源 IV 扫描的完整流程，可直接在联合 GUI 中加载运行。

### 改进

- **文档更新**：`README.md` 新增联合 GUI 的快速开始、项目结构说明与插件接口规范。

## 2026-09-05

### 新增

- **Siglent SVA1032X 频谱仪支持**：新增 `ivlab/instruments/usbtmc_instrument.py`（USB-TMC 通用基类，基于 pyvisa + NI-VISA/Keysight VISA，支持按 VID 自动发现资源）与 `ivlab/instruments/sva1032x.py`（SVA1000X 系列驱动），并附示例 `examples/sva1032x_demo.py`。这类仪器的 USB-B Device 口不是虚拟串口，必须经 VISA 的 USB 驱动访问（资源名形如 `USB0::0xF4EC::0x1032::INSTR`）。

### 修复

- **Keithley 2400 串口无响应**：串口连接时显式拉高 RTS/DTR 握手线，否则仪器不发送任何数据。
- **query() 误读命令回显**：Keithley 2400 的 RS-232 口会回显命令，`query()` 现在自动跳过回显行，避免把回显当作响应解析。

### 改进

- **源模式与测量功能互补**：`set_source_mode` 切换源模式时，自动把测量功能设为互补端并下发 `:SENS:FUNC`（电压源测电流、电流源测电压），同时修正 `_measure_func`，保证 `set_nplc` / `set_range` 作用于正确的物理量。串口（SCPIInstrument）与 GPIB（GPIBSCPIInstrument）两个后端同时生效。
- **互斥校验**：`set_measure_function` 现在拒绝设置与源模式相同的测量功能，并给出明确中文提示。
- **IVScanner 自动推导测量功能**：`setup_instrument` 按 `source_mode` 自动选择互补测量功能，`ScanConfig.measure_func` 字段不再被扫描器使用（保留在配置中不影响兼容）。
