# AGENTS.md — LabEng AI 协作指南

本文件面向两类读者：**使用 AI（如 Kimi Code）在本仓库内生成测试例程的人**，以及**维护本引擎的人**。

## 一句话概述

LabEng 是一个实验室仪器控制引擎：GUI 用「框图」描述 上位机→通信→仪器→测量任务 的连接关系。**测试例程是 `lab_engine/routines/` 目录下的普通 `.py` 文件**，每个例程对应一个「单位测试系统」。引擎启动时递归扫描该目录，凡定义了 `NAME`、`PARAMS`、`run` 三个顶层成员的 `.py` 文件会自动出现在 GUI 的测试系统列表里。**新增例程 = 往该目录放一个符合格式的 .py 文件，无需修改任何现有代码。**

术语分层：
- **测试系统（System）**：一张完整的框图，包括上位机、通信接口、仪器、测量任务节点，保存为 `.labsetup.json`。
- **测量任务（Routine）**：`.py` 例程脚本，只描述「怎么测」，是单位测试系统；一个 Setup 项目可以引用一个或多个测量任务。
- **代码节点（Code Node）**：`lab_engine/commlib/` 下的可复用算法单元（如 DMT/CAP 调制、信道、均衡等），供测量任务在内部调用；对 GUI 框图不可见。

## 给 AI 的任务约定

当用户说「写一个做 XXX 的测试例程」时：

1. 在 `lab_engine/routines/` 下新建一个 `.py` 文件（文件名用英文安全字符，如 `diode_iv.py`）。
2. 严格按下面的「例程文件格式」编写。
3. 写完后用下面的「自检清单」验证（可以直接运行 python 做 exec 检查）。
4. 不要在例程文件里写 `if __name__ == "__main__":` 测试代码；不要 `print`，用 `context.log`。
5. 不要改动 `lab_engine/` 与 `ivlab/` 里的引擎代码，除非用户明确要求。

## 例程文件格式

```python
"""例程的中文文档字符串（显示在 GUI 描述里可填到 DESCRIPTION）。"""
NAME = "二极管正向特性"          # 必填，GUI 下拉框显示的名字，必须全局唯一
DESCRIPTION = "测 1N4148 正向 IV 曲线"  # 可选
ICON = "🔬"                     # 可选

INSTRUMENTS = {                  # 必填，声明本例程要用哪些仪器
    "k2400": {"type": "keithley2400", "required": True},
    # "type" 必须是已注册仪器的 key，见下方「可用仪器」
}

PARAMS = [                       # 必填，可为空列表；GUI 自动生成参数表单
    {"name": "start_v", "label": "起始电压 (V)", "type": "float",
     "default": 0.0, "min": 0.0, "max": 1.0},
    {"name": "points", "label": "点数", "type": "int",
     "default": 51, "min": 2, "max": 10001},
    {"name": "mode", "label": "模式", "type": "choice",
     "choices": ["single", "double"], "default": "single"},
    {"name": "use_guard", "label": "保护环", "type": "bool", "default": False},
]

# type 取值：float / int / str / choice / bool；min/max 可选（GUI 校验越界）


def run(instruments, params, context):
    """例程入口，由引擎在后台线程调用。

    instruments: {"k2400": <已连接的仪器对象>}，键与 INSTRUMENTS 一致
    params:      用户在 GUI 填好的参数字典
    context:     与 GUI 通信的句柄，必须用它的方法上报（见下）
    """
    k2400 = instruments["k2400"]          # required=True 的仪器必然存在

    context.log(f"从 {params['start_v']} V 开始扫描")
    import numpy as np
    for v in np.linspace(params["start_v"], params["stop_v"], params["points"]):
        if context.is_stopped():          # 用户点了「停止」必须响应
            context.log("用户停止", level="warning")
            break
        k2400.set_output_level(v)
        data = k2400.measure()
        context.point(voltage=v, current=data["current"])  # 实时绘图
        context.progress(v, params["points"])              # 进度条

    context.done(success=True)            # 结束必须调用；失败传 success=False
```

### context 可用方法

| 方法 | 作用 |
|------|------|
| `context.log(text, level="info")` | 日志（level: info/warning/error） |
| `context.point(**kwargs)` | 上报一个数据点，右侧图实时绘制 |
| `context.progress(current, total)` | 更新进度条 |
| `context.data(**kwargs)` | 上报最终聚合数据 |
| `context.error(text)` | 上报错误日志 |
| `context.done(success=True)` | **必须调用**，标记例程结束 |
| `context.is_stopped()` | 用户是否请求停止（长循环必须检查） |
| `context.elapsed()` | 已运行秒数 |
| `context.output_dir` | 本次运行的数据输出目录（Path） |

## 可用仪器（INSTRUMENTS 的 type 取值）

| key | 类 | 说明 |
|-----|----|------|
| `keithley2400` | `ivlab.instruments.keithley2400.Keithley2400` | Keithley 2400 源表，RS-232/GPIB |
| `gpd4303s` | `ivlab.instruments.gpd4303s.GPD4303S` | 固纬四通道直流电源 |
| `cornerstone260` | `ivlab.instruments.cornerstone260.Cornerstone260` | Newport 单色仪（DLL） |
| `sva1032x` | `ivlab.instruments.sva1032x.SVA1032X` | 鼎阳频谱/矢网（VISA） |
| `m8190a` | `lab_engine.instruments.m8190a.M8190A` | Keysight 任意波形发生器 |
| `oscilloscope` | `lab_engine.instruments.oscilloscope.Oscilloscope` | Keysight 示波器 |

仪器对象的可用方法见其驱动源码（`ivlab/instruments/*.py`），常见：`set_output_level(v)`、`measure()`、`set_voltage(ch, v)`、`set_current(ch, i)`、`output_on/off()` 等。无硬件调试时用 `ivlab.instruments.mock_keithley2400.MockKeithley2400` 的接口为准。

## 自检清单（生成例程后必做）

```bash
cd <仓库根目录>
python - <<'EOF'
import importlib.util
spec = importlib.util.spec_from_file_location("t", "lab_engine/routines/你的例程.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
assert isinstance(m.NAME, str) and m.NAME
assert isinstance(m.PARAMS, list)
assert callable(m.run)
for p in m.PARAMS:
    assert p.get("name") and p.get("type") in ("float","int","str","choice","bool")
    if p["type"] == "choice": assert p.get("choices")
print("OK")
EOF
```

再在 GUI 里点「🔄 刷新」，确认新测量任务出现在测试系统列表且参数表单正确渲染。

## 引擎结构速览（维护者向）

- `lab_engine/app.py` — 主窗口与三个 Tab（运行 / 测试系统结构 / 测试系统设计）。
- `lab_engine/core/registry.py` — 测量任务（例程）与仪器的注册表；`RoutineRegistry.discover()` 递归扫描例程目录，`last_report` 记录加载成败。
- `lab_engine/core/system_registry.py` — 测试系统注册表，合并 `.py` 单位系统与 `.labsetup.json` 组合系统。
- `lab_engine/core/setup_graph.py` — 框图数据模型（节点/边/序列化）。
- `lab_engine/core/routine_context.py` — 测量任务运行时上下文（上表所列方法的实现）。
- `lab_engine/core/param_store.py` — 每个任务的用户参数持久化（`data/routine_params.json`）。
- `lab_engine/gui/setup_panel.py` — 框图编辑器（节点绘制、拖拽、连线、向导、保存）。
- `lab_engine/gui/routine_panel.py` — 运行页的系统选择与参数表单（按 PANEL 描述排序/隐藏参数）。
- `lab_engine/commlib/` — 通信/信号处理代码节点库（DMT、CAP 等），供测量任务内部调用。
- `lab_engine/paths.py` — 路径统一入口（开发=仓库根；打包 exe 后=exe 旁边）。
- `ivlab/` — 底层仪器驱动与扫描器（SCPI/TSP/GPIB/VISA 封装）。

## 例程文件里的可选高级字段

- `SETUP_GRAPH`（dict）— 保存时的框图快照，GUI「例程结构」页按它还原布局。**现在保存在 `.labsetup.json` Setup 项目文件中，由「测试系统设计」Tab 写入；手写例程不要加。**
- `PANEL`（dict）— 操作面板描述（分区/标题/参数显隐）。**同样保存在 `.labsetup.json` 项目文件中**，运行页按它渲染参数表单。

## 代码节点库（commlib）

`lab_engine/commlib/` 是测量任务内部可复用的算法单元库，目前包含：

- `dmt/` — DMT 调制/解调、IFFT/FFT、星座映射、虚拟信道、画图/保存等节点。
- `cap/` — 单带/多带 CAP 收发链路、Volterra/LMS/NN 均衡、星座图画图等节点。
- `executor.py` — 按有向图拓扑执行代码节点。
- `registry.py` — 合并各库节点注册表。

这些节点**不直接出现在 GUI 框图里**，而是供 `.py` 测量任务在 `run()` 内部调用。例如 `lab_engine/routines/communication/dmt_lowcode_tx.py` 演示如何用代码节点拼一条离线 DMT 发射链路。

> 注：`lab_engine/commlib/superposition/` 目录已复制但尚未接入注册表，等算法稳定后再合并。

## AI 生成/检查例程的提示词模板

如果你（或学弟学妹）想用 AI 生成测量任务，建议把下面的提示词填进 Kimi / Codex / ChatGPT，让 AI 按统一格式输出。生成后，Agent 也会按同样的清单检查。

```text
你正在为一个实验室仪器控制软件 LabEng 编写测量任务（Routine）。
测量任务是 lab_engine/routines/ 目录下的普通 Python 文件，代表一个单位测试系统，必须满足：

1. 文件顶层定义：
   - NAME：唯一的中文名字字符串，会显示在 GUI 的测试系统列表。
   - DESCRIPTION：简短描述字符串（可选）。
   - ICON：单个 emoji 字符串（可选）。
   - INSTRUMENTS：字典，key 是仪器别名，value 是 {"type": 仪器类型, "required": true/false}。
   - PARAMS：参数列表，每项是 {"name": ..., "label": ..., "type": "float|int|str|choice|bool", "default": ...}，choice 类型必须带 "choices"。

2. 必须实现函数：
   def run(instruments, params, context):
       """测量任务入口。"""
       ...

3. 约束：
   - 不要写 if __name__ == "__main__": 测试块。
   - 不要直接用 print，统一用 context.log(text, level="info|warning|error")。
   - 长循环里必须检查 context.is_stopped()，用户点击停止时立即退出。
   - 每个数据点用 context.point(**kwargs) 上报。
   - 用 context.progress(current, total) 更新进度条。
   - 函数最后必须调用 context.done(success=True) 或 context.done(success=False)。
   - 仪器对象只能从 instruments 字典取，不要自己实例化。

4. 任务描述：
   [在这里填写实验意图：使用什么仪器、是否同步触发、扫参范围、测量什么、如何保存/绘图、是否多仪器联动等]

请直接输出完整可运行的 .py 文件内容，不要加额外解释。
```

生成后请运行下面的自检脚本验证结构：

```bash
python - <<'EOF'
import importlib.util
spec = importlib.util.spec_from_file_location("t", "lab_engine/routines/你的例程.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
assert isinstance(m.NAME, str) and m.NAME
assert isinstance(m.PARAMS, list)
assert callable(m.run)
for p in m.PARAMS:
    assert p.get("name") and p.get("type") in ("float","int","str","choice","bool")
    if p["type"] == "choice": assert p.get("choices")
print("OK")
EOF
```

## 添加一台新仪器（维护者向）

1. 在 `ivlab/instruments/`（或 `lab_engine/instruments/`）写驱动类，实现连接/读写方法。
2. 在 `lab_engine/instruments/__init__.py` 里 `InstrumentRegistry.register(key=..., cls_type=..., name=..., connection_params=[...], description=...)`。
3. 例程即可通过 `INSTRUMENTS = {"别名": {"type": "你的key"}}` 使用。

## 打包与发布

- 双击 `build_exe.bat` 生成 `dist/LabEng/LabEng.exe`（需 `pip install pyinstaller`）。
- `dist/LabEng/` 里已附带 `routines/` 目录；使用者把新例程 .py 丢进去、点「🔄 刷新」即可用。
