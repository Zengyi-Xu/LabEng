# LabEng 教材 —— 如何读懂、修改和扩展这套代码

> 写给后来的学弟学妹：你手里的这个软件控制过实验室里真实的仪器。
> 它从几十行串口脚本长成现在带图形界面的插件化引擎，整个过程都保留在 git 历史里。
> 这本教材按"它是什么 → 怎么长出来的 → 里面长什么样 → 怎么动手改"的顺序讲，
> 你只需要 Python 基础，不需要 GUI 或仪器通信的经验。

---

## 第 0 章 这个项目是什么

一句话：**用框图搭实验系统、用插件写测试流程的仪器控制软件**。

实验室里的自动化测试 traditionally 长这样：每人拷一份别人改过的 Python 脚本，
改里面的串口号、电压范围、循环次数，跑挂了再改，没人知道哪份是最新版。
LabEng 想解决这个问题，它把"实验系统"和"测试流程"分开：

- **系统**（哪台电脑、哪条总线、哪些仪器怎么连）用框图画出来，存进例程文件；
- **流程**（先加偏置再扫 IV 还是反过来）写成例程插件，一个 `.py` 文件一个功能；
- 不会写代码的人：向导搭框图 → 填参数 → 点运行；
- 会写代码的人：写一个 `.py` 丢进 `routines/` 就发布了新功能；
- 想偷懒的人：让 AI 读 `AGENTS.md` 帮你写。

## 第 1 章 它是怎么长出来的（开发史）

读别人的代码最难的是"为什么这么设计"。这一章讲每个设计决策背后的原因，
git log 里能对应到每次变更。理解发展史 = 理解架构。

### 第一阶段：脚本（RS-232 直连）

最早的形态：一个脚本开串口、发 SCPI 指令、存 CSV。
问题很快出现——每个仪器一套脚本，换台电脑串口号变了全文搜索替换；
仪器指令散落在各处，Keithley 的 `SENS:CURR:PROT` 和 GPD 的 `VSET` 混在一起。

**教训 1：仪器通信细节必须和实验逻辑分离。**

### 第二阶段：驱动库（`ivlab/`）

把每个仪器封装成类：`Keithley2400.set_voltage(v)`、`measure()`。
脚本只跟对象打交道，不再见裸指令。又进一步把"扫描"这种通用流程抽象成
`ivlab/scanner/`（IVScanner、Hysteresis、WavelengthScanner），
配置用 dataclass（`ScanConfig`），数据自动存 CSV。

**教训 2：通用流程（扫描、平均、存盘）和具体实验（测什么、判什么）也要分开。**

### 第三阶段：引擎（`lab_engine/`）

有了驱动库，新问题变成：每来一个新实验就要写一个新脚本 + 一个新 GUI？
决定做插件化：

- **注册表模式**（`core/registry.py`）：启动时扫描 `routines/` 目录，
  凡是定义了 `NAME`/`PARAMS`/`run` 的 `.py` 自动成为例程。
  这是整个项目最重要的一次决策——它让"加功能"从"改代码"变成"加文件"，
  也让 AI 生成例程成为可能（AI 只需要会写一个格式正确的文件）。
- **参数声明式**：例程用 `PARAMS` 列表描述要哪些参数（名字/类型/范围/默认值），
  GUI 据此自动生成表单，并自动校验越界。写例程的人不需要懂 GUI。
- **运行时上下文**（`core/routine_context.py`）：例程在后台线程跑，
  通过 `context.log()` / `context.point()` 等线程安全的方法和界面通信。
  例程作者不需要懂多线程。

### 第四阶段：图形化（三个 Tab）

光有参数表单还不够，"这台仪器接哪根线"这种信息文字说不清。
于是有了框图编辑器（`gui/setup_panel.py`，约 2500 行，本项目最复杂的模块）：

- 节点 = 上位机 / 通信接口 / 仪器 / 例程，拖线即连接；
- 框图不再单独存文件——**保存时序列化进例程 `.py`**（`SETUP_GRAPH` 变量），
  例程文件成为唯一事实来源，"例程结构"页按它 1:1 还原布局；
- 面板布局（哪些参数显示、什么顺序）也存进 `.py`（`PANEL` 变量），
  运行页所见即所得。

**教训 3：一个事实只存一处。曾经框图存 `.labsetup.json`、代码存 `.py`，
两个保存按钮把用户搞糊涂；合并成一个「💾 保存」后世界清净了。**

### 第五阶段：交接打磨（最近两轮迭代）

功能基本稳定后，全部精力投向"别人能不能接手"：
单一上位机约束、画布锁定、加载失败弹窗、参数持久化、自动草稿、
`AGENTS.md`（AI 协作约定）、exe 打包。判断标准从"能不能用"变成
"一个不熟的人（或一个 AI）能不能不问我就在上面干活"。

## 第 2 章 架构总览

```
┌────────────────────────── GUI（主线程，tkinter）──────────────────────────┐
│  app.py 主窗口                                                             │
│  Tab1 运行:  routine_panel(选例程/参数) + connection_panel(连仪器)          │
│               + plot_panel(实时图) + log_panel(日志)                       │
│  Tab2 例程结构: view_setup_panel（只读框图，从 SETUP_GRAPH 还原）           │
│  Tab3 设计:   edit_setup_panel（框图编辑器 + 向导 + 保存）                  │
└──────────────┬──────────────────────────────────────────────┬─────────────┘
               │ 启动时扫描                                    │ 运行时
               ▼                                               ▼
┌────────────────────────── core（数据与调度）───────────────────────────────┐
│  registry.py   例程/仪器注册表（插件发现的入口）                            │
│  setup_graph.py 框图数据模型（Node/Edge/序列化/校验）                       │
│  routine_context.py  后台线程→GUI 的线程安全通信                            │
│  param_store.py      参数持久化(JSON)        data_manager.py 数据存盘       │
└──────────────┬─────────────────────────────────────────────────────────────┘
               │ 例程通过 instruments[alias] 拿到驱动对象
               ▼
┌────────────────────────── ivlab（仪器驱动层）───────────────────────────────┐
│  instruments/  每个仪器一个类（SCPI/TSP/GPIB/VISA 封装）                     │
│  scanner/      通用扫描流程（IV/回滞/波长）                                  │
└────────────────────────────────────────────────────────────────────────────┘

例程插件（routines/*.py）：被 registry 扫描发现，跑在后台线程，
是唯一会被"用户/AI 频繁新增"的层。
```

记住这条依赖链：**GUI → core → ivlab → 硬件；例程插件挂在 core 层，被 GUI 发现。**
依赖严格单向，改下层不影响上层。

## 第 3 章 读代码路线（建议顺序）

不要从 `setup_panel.py` 开始（2500 行会把人劝退）。按下面顺序，每层 1-2 小时：

### 第 1 步：跑起来，当一个用户（0.5 天）

按 README 跑通全流程：向导建项目 → 选 mock 仪器 → 保存 → 运行。
带着三个问题读体验：
- 参数表单是**自动**来的——谁生成的？（答：`routine_panel.py` 读 `PARAMS`）
- 例程列表是**自动**来的——谁发现的？（答：`registry.py` 的 `discover()`）
- 例程在后台跑，曲线却实时画——怎么通信的？（答：`routine_context.py` 的 queue）

### 第 2 步：读一个例程（1 小时）

`lab_engine/routines/bias_iv_sweep.py`（约 100 行，注释最全）。
它演示了全部插件 API：声明仪器、声明参数、写 run()、用 context 上报。
读完试着回答：如果把 `scan_type` 的 `"sweep"` 从 choices 里删掉会发生什么？
（GUI 表单立刻少一个选项——声明即界面。）

### 第 3 步：读注册表（1 小时）

`core/registry.py`（约 160 行）。重点三个类：
- `InstrumentRegistry`：类级字典，`register()` 时元数据入库；
- `RoutineRegistry.discover()`：`rglob("*.py")` → `importlib` 动态加载 →
  检查 `NAME/PARAMS/run` → 入库；`last_report` 记录成败；
- `RoutineMeta`：例程的"档案"，`setup_graph`/`panel` 字段存内嵌的框图/面板。

动态加载看不懂的话，先读 Python 官方 `importlib` 文档的
spec_from_file_location 一节，10 分钟。

### 第 4 步：读运行时上下文（1 小时）

`core/routine_context.py`（73 行，全书最短却最关键）。
`app.py` 里的 `_RoutineWorker`（threading.Thread）在后台 `exec` 例程的 `run()`，
例程只能通过 context 的 queue 往外发消息；GUI 主线程 `after()` 轮询 queue。
这就是"例程作者不需要懂线程"的实现方式。

### 第 5 步：读框图数据模型（2 小时）

`core/setup_graph.py`（约 400 行）。纯数据类，无 GUI：
Node/Edge 的 dataclass、`to_dict/from_dict` 序列化、`validate_status()` 校验
（比如"routine 的仪器端口没连线就标红"）。
看懂它你就知道 SETUP_GRAPH 存的是什么。

### 第 6 步：读框图编辑器（分三次，每次 1 小时）

`gui/setup_panel.py` 很大，按功能块读，别线性通读：
1. 数据→屏幕坐标：`_to_screen/_from_screen/_node_size`（理解 zoom 和 DPI scale 是后面一切的基础）；
2. 绘制：`_draw_node/_draw_edge`（canvas item + tag 系统）；
3. 交互：`_on_canvas_press/drag/release`（拖拽、框选、连线、整组移动）。

## 第 4 章 核心机制精讲

### 4.1 插件发现（最重要）

```python
# registry.py discover() 的核心循环
for py_file in sorted(path.rglob("*.py")):
    if py_file.name.startswith("_"):
        continue
    meta = self._load_routine(py_file)   # exec 文件，检查必需属性
    if meta:
        self._routines[meta.name] = meta
```

三个设计点：递归扫描（子目录也能放例程）；下划线开头跳过（`__init__.py`）；
重复 NAME 后者覆盖前者并告警。**这就是"即插即用"四个字的全部实现，总共不到 20 行。**

### 4.2 声明式参数

```python
PARAMS = [{"name": "start_v", "label": "起始电压 (V)", "type": "float",
           "default": -1.0, "min": -200.0, "max": 200.0}]
```

`routine_panel._make_param_widget()` 按 `type` 分派生成 Entry/Combobox/Checkbutton，
`validate_params()` 按 `min/max` 校验。新增参数类型 = 在两个方法里加一个分支。

### 4.3 例程与 GUI 的线程边界

后台线程能调 `context.point()`，绝不能直接碰 tkinter 控件（tk 不是线程安全的）。
context 的所有方法都只是 `queue.put`，GUI 侧 `after(100ms)` 轮询——
这是教科书级的"生产者-消费者 + 事件循环"模式。

### 4.4 例程文件即数据库

保存 = 渲染一个 `.py` 模板，把框图字典和面板字典用 `repr()` 嵌进去：

```python
NAME = "偏置 IV 扫描"
PARAMS = [...]
SETUP_GRAPH = {'version': 1, 'nodes': [...], 'edges': [...]}   # 由 LabEng 写入，勿手改
PANEL = {'title': ..., 'sections': [...], 'hidden_params': [...]}
```

加载 = `exec` 文件 + `getattr(module, "SETUP_GRAPH", None)`。
一个文件同时是代码、数据、布局、界面配置——好处是**发一个文件就发了全部**。

## 第 5 章 动手实验（从读到改）

按顺序做，每个实验半天以内。做完你就具备了维护能力。

- **实验 1（改例程）**：复制 `basic_iv_scan.py` 改名 `my_first.py`，
  加一个叫 `delay_s` 的 float 参数，在 run() 里 `import time; time.sleep(params["delay_s"])`。
  刷新 GUI，确认表单多了一栏。→ 你掌握了插件 API。
- **实验 2（写例程）**：不参考现有代码，按 `AGENTS.md` 的格式从零写一个
  "让 GPD 输出 5V 然后读 10 次数" 的例程，用自检脚本验证。→ 你掌握了发布流程。
- **实验 3（修 bug）**：故意在例程里把 `PARAMS` 写成字符串而非列表，
  刷新，观察「🔄 刷新」弹出的错误汇总。→ 你掌握了诊断流程。
- **实验 4（读 GUI）**：在 `_on_canvas_drag` 里加一行 `print(event.x, event.y)`，
  拖动节点看输出，然后删掉。→ 你摸到了编辑器的心跳。
- **实验 5（改引擎）**：给 PARAMS 新增一种 `type: "text"`（多行字符串），
  需要改 `routine_panel._make_param_widget` 和 `validate_params` 两处。
  改完用 mock 例程验证。→ 你打通了"数据声明 → 界面 → 校验"全链路。

## 第 6 章 用 AI 辅助（本项目的设计意图之一）

`AGENTS.md` 是写给 AI 的"接口文档"：格式约定、可用仪器表、自检脚本。
典型用法：用 Kimi Code 打开本仓库文件夹，说

> "按 AGENTS.md 的约定，写一个测 1N4148 正向导通压降的例程，用 keithley2400"

AI 会生成文件并跑自检；你刷新 GUI 就能用。**但你要会验收**（第 5 章实验 3 的技能）：
检查 NAME 是否冲突、INSTRUMENTS 的 type 是否合法、run() 里有没有 while 死循环没查 `is_stopped()`。
AI 是放大器，不是替身。

## 第 7 章 调试与常见问题

| 现象 | 排查 |
|------|------|
| 新例程不出现在下拉框 | 点「🔄 刷新」看错误汇总；文件是否定义了 NAME/PARAMS/run；文件名是否 `_` 开头 |
| 例程跑起来没图 | run() 里是否调了 `context.point(...)` |
| 点停止没反应 | 循环里是否检查 `context.is_stopped()` |
| 画布上连线看不见 | 已修（高 DPI 坐标 bug）；若复现看 `_draw_temp_edge` 的坐标换算 |
| 仪器连不上 | `docs/instrument_errors.md`；先换 mock 模式确认例程逻辑没问题 |
| exe 打不开/被杀毒拦截 | 加信任区；确认 `routines/` 与 exe 同级 |

日志在 `logs/`，数据在 `data/`，参数记忆在 `data/routine_params.json`（可直接编辑重置）。

## 第 8 章 如果继续往下做

按价值排序的候选方向（都是真实需求，不是镀金）：

1. **PANEL 自由布局**：目前面板是分区列表；下一步是拖控件摆位置的自由设计器。
2. **多例程编排**：把几个例程串成"先老化再扫描"的序列，涉及例程间数据传递。
3. **数据回放**：把 `data/` 里的 CSV 拖进图区直接对比历史曲线。
4. **多上位机**：框图模型本来就支持多个 host 节点（当前被约束为一个），
   真做多机协同时放开约束 + 加网络传输层即可。
5. **测试补强**：`core/` 已可独立测试，补 pytest 套件 + CI。

## 结语

这套代码最值得带走的不是功能，是三个可复用的思想：
**目录扫描 = 插件系统**（20 行代码换来无限扩展性）；
**声明式参数 = 自动生成界面**（数据即 UI）；
**例程文件 = 代码+数据+布局的唯一事实来源**（分发与版本管理的极致简化）。

 Instruments come and go, protocols change, but these ideas will still be useful
whatever you build next. 祝调试愉快。
