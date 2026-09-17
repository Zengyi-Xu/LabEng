# LabEng 代码说明文档

本文档面向后续维护本项目的同学。内容分四部分：项目结构、开发历程中做出的主要设计决定、各模块的读法、以及可以动手做的练习。阅读本文档不需要 GUI 编程或仪器通信的经验，但需要基本的 Python 知识。

---

## 第一部分 项目结构

LabEng 是一个实验室仪器控制软件。它的工作方式是把实验系统表示成一张框图：上位机、通信接口、仪器、测量任务各自是一个节点，节点之间的连线表示控制和数据流向。用户在「测试系统设计」页搭好框图并保存为 `.labsetup.json` 项目文件，在「运行」页选中一个测试系统（单位系统 = 单个 `.py` 测量任务；组合系统 = `.labsetup.json` 项目）、连接仪器、填写参数后即可执行。

代码分为五层，依赖关系是单向的：

```
GUI 层        lab_engine/gui/       三个 Tab 的界面代码
引擎层        lab_engine/core/      注册表、框图数据模型、运行时上下文、参数持久化
驱动层        ivlab/                仪器驱动（SCPI / TSP / GPIB / VISA 封装）与扫描器
插件层        lab_engine/routines/  测量任务（例程），每个 .py 文件一个
代码节点层    lab_engine/commlib/   通信/信号处理算法单元，供测量任务内部调用
```

上层调用下层，下层不依赖上层。修改驱动层不会影响 GUI；新增测量任务只需要在 routines 目录下添加文件，不需要改动其他代码。

界面分三个 Tab：

- 运行：选择测试系统、连接仪器、填写参数、执行、查看实时曲线和日志。
- 测试系统结构：只读显示当前 Setup 项目框图。如果已加载 `.labsetup.json`，这里按项目里的 `SETUP_GRAPH` 还原布局。
- 测试系统设计：框图编辑器。新建项目向导、节点编辑、连线、面板配置、保存 `.labsetup.json` 都在这个页面完成。

## 第二部分 主要设计决定

这一节按时间顺序说明开发过程中几个关键决定的原因。

### 1. 仪器通信与实验逻辑分离

最早的形式是直接操作串口的脚本。每个仪器一套脚本，仪器指令散落在各处。后来把每个仪器封装成一个类，脚本只与对象打交道。这一步产生了 ivlab 包，也是整个项目的地基。

### 2. 通用流程与具体实验分离

驱动类写好之后，扫描、平均、数据存盘这类流程又被抽象到 ivlab/scanner/。配置用 dataclass 表示。这样"怎么扫"和"扫出来判断什么"分开了。

### 3. 例程插件化

有了驱动和扫描器之后，每增加一个实验仍然要写新脚本和新界面。于是把例程做成插件：例程是 routines/ 目录下的普通 .py 文件，定义 NAME、PARAMS、run 三个顶层成员。引擎启动时递归扫描这个目录，加载所有符合格式的文件。

这个决定是后续一切扩展性的基础。加功能等于加文件，不改引擎。AI 生成例程也因此成为可能：AI 只需要写一个格式正确的文件。

### 4. 参数声明式

例程用 PARAMS 列表声明需要哪些参数，每项包含名字、显示名、类型、默认值和可选的范围。GUI 根据这个列表自动生成参数表单，并在运行前校验越界。写例程的人不需要了解界面代码。

### 5. 例程在后台线程运行

例程执行时不允许阻塞界面，所以跑在后台线程里。例程通过 RoutineContext 对象与界面通信：log、point、progress、done 等方法内部都是往队列里放消息，GUI 主线程定时从队列取出并更新界面。例程作者不需要处理任何线程问题，context 的文档见 routine_context.py。

### 6. Setup 项目、测量任务与代码节点三层分离

框图编辑器的保存结果写进 `.labsetup.json` 项目文件：里面包含节点、连线、仪器别名、通信参数、PANEL 面板配置等。测量任务脚本是 `lab_engine/routines/` 下的普通 `.py` 文件，只包含 `NAME`、`INSTRUMENTS`、`PARAMS`、`run()`，负责"怎么测"。代码节点是 `lab_engine/commlib/` 下的可复用算法单元（DMT/CAP 调制、信道、均衡等），供测量任务在 `run()` 内部调用，负责"具体信号处理怎么做"。

一个 Setup 项目可以引用一个或多个测量任务，同一个任务也可以被多个 Setup 项目引用。早期版本框图存在单独的 `.labsetup.json` 文件里，后来一度把 `SETUP_GRAPH` 和 `PANEL` 合并写进例程 `.py` 文件，导致例程文件变成"脚本 + 设计图 + 面板配置"的混合物。现在重新拆回三个层次：`.labsetup.json` 负责"用什么系统测、界面怎么呈现"，`.py` 负责"怎么测"，`commlib` 负责"底层算法"。

### 7. 面向交接的打磨

功能稳定之后，开发重点转向可交接性：例程重名检测、加载失败弹窗、参数持久化、自动保存草稿、AGENTS.md（AI 协作约定）、exe 打包。判断标准从"能不能用"变成"不熟这个项目的人或 AI 能不能不询问原作者就完成常见任务"。

## 第三部分 各模块读法

建议按下面的顺序读，每层一到两个小时。setup_panel.py 有两千多行，不要从头顺序读，按功能块读。

### 1. 先跑起来

按 README 的步骤跑一遍完整流程：在「测试系统设计」Tab 新建项目、选择已有测量任务节点、搭框图、保存 `.labsetup.json`；切换到「运行」Tab 选择测试系统、选择 mock 仪器、运行。跑的时候留意三个问题：参数表单是谁生成的（routine_panel.py 读 PARAMS，PANEL 来自 Setup 项目），测试系统列表是谁发现的（core/system_registry.py 合并 registry.py 的例程与磁盘上的 .labsetup.json），后台线程的例程为什么能实时更新界面（core/routine_context.py 的队列）。

### 2. 读一个例程

lab_engine/routines/bias_iv_sweep.py，一百行左右，是注释最完整的例程。它演示了插件 API 的全部内容：声明仪器、声明参数、写 run()、用 context 上报数据和进度。

### 3. 读注册表

core/registry.py，一百六十行左右。三个重点：InstrumentRegistry 是类级字典，register 的时候元数据入库；RoutineRegistry.discover() 递归扫描 routines 目录，用 importlib 动态加载每个 .py 文件，检查 NAME、PARAMS、run 三个属性，通过的进入注册表，失败的记入 last_report；RoutineMeta 是例程脚本的档案，只包含代码元数据（NAME、PARAMS 等），框图和面板配置现在保存在 .labsetup.json 项目文件里。

动态加载用到 importlib.util.spec_from_file_location，不理解的话可以先看 Python 官方文档中这一节的说明。

### 4. 读运行时上下文

core/routine_context.py，七十多行。app.py 里的 _RoutineWorker 线程调用例程的 run()，例程只能通过 context 的方法往外发消息，GUI 主线程每 100 毫秒轮询一次队列。这是生产者-消费者模式加一个定时器。

### 5. 读框图数据模型

core/setup_graph.py，四百行左右。纯数据类，与界面无关。Node 和 Edge 的序列化、validate_status() 的校验规则（比如测量任务节点的仪器端口没有连线就标红）都在这里。读懂它就知道 SETUP_GRAPH 里存的是什么。

### 6. 读框图编辑器

gui/setup_panel.py 按三个功能块读：

- 坐标换算：_to_screen、_from_screen、_node_size。zoom 和 DPI scale 的概念是后面一切的基础。
- 绘制：_draw_node、_draw_edge。用到 canvas 的 item 和 tag 机制。
- 交互：_on_canvas_press、_on_canvas_drag、_on_canvas_release。拖拽、框选、连线、整组移动都在这里。

### 7. 读代码节点库

`lab_engine/commlib/` 是测量任务内部调用的算法单元库，与 GUI 框图解耦。关键文件：

- `registry.py`：合并 DMT/CAP 等库的节点注册表。
- `executor.py`：`run_graph()` 按拓扑顺序执行节点图，节点输出通过 `inputs`/`outputs` 传递。
- `dmt/nodes.py`、`cap/nodes.py`：把原有 MATLAB/Python 算法封装成带输入/输出/参数的节点。
- `dmt/main_dmt.py`、`cap/main_cap.py`：保留原始离线仿真入口，节点函数内部调用它们。

读一个示例任务 `lab_engine/routines/communication/dmt_lowcode_tx.py`，看它如何把代码节点串成一条完整测量链路。

> 注：`lab_engine/commlib/superposition/` 已复制但尚未接入注册表，等算法稳定后再合并。

## 第四部分 动手练习

按顺序做，每个练习半天以内。

练习一：复制 `docs/routine_template.py` 到 `lab_engine/routines/my_first.py`，改名并修改 `NAME`，加一个 float 类型的参数 `delay_s`，在 `run()` 里 `time.sleep(params["delay_s"])`。刷新 GUI，确认表单多了一栏。做完这个练习就掌握了插件 API。

练习二：不看现有例程，按 AGENTS.md 的格式从零写一个例程：让 GPD 输出 5V，然后读 10 次数。用 AGENTS.md 里的自检脚本验证。做完这个练习就掌握了发布流程。

练习三：故意把某个例程的 PARAMS 写成字符串而不是列表，刷新界面，观察刷新按钮弹出的错误汇总。做完这个练习就掌握了诊断流程。

练习四：在 _on_canvas_drag 里加一行 print(event.x, event.y)，拖动节点观察输出，然后删掉。做完这个练习就摸到了编辑器交互代码的位置。

练习五：给 PARAMS 新增一种 type: "text"（多行字符串）。需要改 routine_panel.py 的 _make_param_widget 和 validate_params 两处。改完用 mock 例程验证。做完这个练习就走通了从数据声明到界面到校验的完整链路。

## 第五部分 后续可做的方向

按价值排序：

1. PANEL 自由布局：目前面板是分区列表形式，下一步可以做拖控件摆位置的自由设计器。
2. 多例程编排：把几个例程按顺序组成一次完整的测试，涉及例程之间的数据传递。
3. 数据回放：把 data/ 目录里的 CSV 文件拖进绘图区，与当前曲线对比。
4. 多上位机：框图模型本身支持多个 host 节点，当前约束为一个。如果将来需要多机协作，放开约束并增加网络传输层。
5. 单元测试：core/ 目录的模块不依赖界面，可以独立测试，补上 pytest 套件和持续集成。

## 附：文档索引

- README.md：使用说明。
- AGENTS.md：AI 生成测量任务的格式约定、可用仪器清单、提示词模板和代码节点说明。
- docs/routine_template.py：最小可运行测量任务模板，复制到 lab_engine/routines/ 下修改即可。
- docs/AI_COLLABORATION.md：使用 AI 辅助开发本项目的流程与纪律。
- docs/simulation_report.md、docs/iteration2_report.md：各轮迭代的测试记录。
