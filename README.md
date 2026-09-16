# IVLab — 多仪器自动化测试框架

基于 Python + RS-232/USB/GPIB 的多仪器控制框架，支持 Keithley 2400/2450/2600B 源表的 IV 曲线实时扫描、回滞分析、多次平均降噪（2400 支持 RS-232 与 GPIB/NI488），以及 Cornerstone 260 单色仪的 USB/RS-232 通信与波长扫描，并预留 Newport 2359-R 光功率计扩展接口。

---

## 功能特性

| 功能 | 状态 | 说明 |
|------|------|------|
| **Keithley 2400** | ✅ 完整 | SCPI 指令集，支持 RS-232 与 GPIB/NI488 |
| **Keithley 2450** | ✅ 完整 | 自动切换至 2400 SCPI 兼容模式 |
| **Keithley 2600B** | ✅ 完整 | TSP/Lua 脚本模式（`smua`/`smub`） |
| **双向扫描** | ✅ 完整 | 正向 + 反向，形成闭合 I-V 环 |
| **往返扫描** | ✅ 完整 | 0 → Vmax → 0 → -Vmax → 0 |
| **多次平均** | ✅ 完整 | N 次重复扫描，支持方向随机化 |
| **回滞分析** | ✅ 完整 | 回滞面积、回滞指数、最大 ΔI、对称因子 |
| **实时绘图** | ✅ 完整 | matplotlib 动态 I-V 曲线 + ΔI 分析图 |
| **CSV 保存** | ✅ 完整 | 含元数据头，Excel 可直接打开 |
| **多仪器协调** | ✅ 完整 | 扫描序列定义，支持并行读取 |
| **CS260 USB** | ✅ 完整 | Newport 官方 DLL 桥接（32 位 PowerShell 子进程） |
| **CS260 RS-232** | ✅ 完整 | ASCII 指令集（`WAVE`/`SHUTTER`/`GRAT`），轮询到位判定 |
| **SVA1032X USB** | ✅ 完整 | Siglent 频谱/矢量网络分析仪，USB-TMC（NI-VISA），SA/VNA 模式 |
| **波长扫描** | ✅ 完整 | 单向/往返波长扫描，可同步读光功率计，CSV 保存 |
| **2359-R 预留** | 📝 接口 | 协议待填入 `optical_power_meter.py` |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

依赖：`pyserial`, `pyvisa`, `numpy`, `matplotlib`, `pandas`

### 2. 基础 IV 扫描

```bash
python examples/basic_iv_scan.py              # RS-232
python examples/basic_iv_scan.py --gpib 22    # GPIB 地址 22
```

程序会自动扫描可用 COM 端口（RS-232 模式），交互式选择后执行单向电压扫描；加 `--gpib` 则通过 GPIB/NI488 控制。

### 3. 回滞扫描与分析

```bash
python examples/hysteresis_scan.py
```

执行双向扫描（正向 + 反向），自动计算回滞面积、回滞指数，并生成对比图。

### 4. 波长扫描（Cornerstone 260）

```bash
python examples/wavelength_scan.py --start 400 --stop 410 --step 2
```

自动连接 USB 接口的 CS260（或加 `--port COMx` 使用 RS-232），执行波长扫描并保存 CSV。

### 5. 多仪器协调（演示）

```bash
python examples/multi_device_demo.py
```

展示如何定义多仪器扫描序列（单色仪 → 源表 → 光功率计）。

### 6. SVA1032X 频谱/矢网控制

```bash
python examples/sva1032x_demo.py                # VNA 模式 (S21)
python examples/sva1032x_demo.py --mode sa      # 频谱分析模式
```

通过 USB-B（USB-TMC）连接，自动发现 Siglent 设备；设置模式、扫频范围、
幅值刻度、Marker 位置/模式/参考点并读取 Marker 读数。

### 7. GPD-4303S 直流电源控制（USB-B）

```bash
python examples/gpd4303s_demo.py              # 交互式选择 COM 口
python examples/gpd4303s_demo.py --port COM3  # 指定 COM 口
python examples/gpd4303s_gui.py               # 图形化监控面板
```

GPD-4303S 的 USB-B 口在 Windows 上表现为虚拟串口（默认波特率 9600），示例
演示设置 CH1/CH2/CH4 电压电流、开启总输出、循环读取实际输出并保存 CSV。
GUI 版本可实时显示四个通道的电压/电流/模式与总输出状态，适配高 DPI 屏幕。

### 8. K2400 + GPD4303S 联合测试例程 GUI

```bash
python examples/k2400_gpd4303s_routine_gui.py
```

在同一面板中同时连接 Keithley 2400 与 GPD4303S，实时显示两台仪器的读数与
连接状态。通过“加载例程文件”导入 Python 插件（见 `examples/routines/`），
即可按自定义参数执行多仪器联动测试（如 GPD 提供偏置、K2400 执行 IV 扫描）。
运行过程中实时绘制 I-V 曲线，测试结束后自动保存 CSV 与 JSON 元数据。

### 9. Lab Engine（通用仪器引擎，实验性）

```bash
python lab_engine_app.py
# 或
python -m lab_engine
```

Lab Engine 是 IVLab 向“插件化实验平台”演进的第一步。它提供一个统一的 GUI 外壳：

- 自动按例程声明渲染仪器连接面板
- 自动按例程声明渲染参数面板
- 后台线程运行例程，实时显示日志、进度和曲线
- 每次运行自动生成 `data/<run_id>/data.csv` 与 `metadata.json`

Phase 2 内置例程：

| 例程 | 文件 | 所需仪器 | 说明 |
|------|------|----------|------|
| 偏置 IV 扫描 | `lab_engine/routines/bias_iv_sweep.py` | K2400 + GPD4303S | GPD 提供偏置，K2400 执行 IV 扫描 |
| 基础 IV 扫描 | `lab_engine/routines/basic_iv_scan.py` | K2400 | 单向/双向/往返 IV 扫描 |
| 回滞扫描分析 | `lab_engine/routines/hysteresis_scan.py` | K2400 | 双向扫描 + 回滞面积/指数/对称因子 |
| 单色仪 IV 联动 | `lab_engine/routines/mono_iv_scan.py` | CS260 + K2400 | 扫波长，K2400 固定电压读电流 |
| 波长扫描 | `lab_engine/routines/wavelength_scan.py` | CS260 | Cornerstone 260 波长扫描 |
| SVA1032X VNA | `lab_engine/routines/sva1032x_vna.py` | SVA1032X | S11/S21 测量 + Marker 读数 |
| DMT 网格扫描 | `lab_engine/routines/communication/grid_scan.py` | K2400 (+ AWG/示波器) | 偏置 × Vpp 二维扫描，运行 DMT pipeline |
| DMT 完整流程 | `lab_engine/routines/communication/dmt_pipeline.py` | AWG/示波器（可选） | QPSK 信道探测 → bitloading → 解调 |
| NN 后均衡 | `lab_engine/routines/communication/nn_equalize.py` | — | 运行 ZY_BiGRU_GPU 神经网络均衡 |

已注册仪器：`keithley2400`、`gpd4303s`、`cornerstone260`、`sva1032x`、`m8190a`、`oscilloscope`。

> **Setup 框图**：`lab_engine/core/setup_graph.py` 与
> `lab_engine/gui/setup_panel.py` 已重构为可视化节点编辑器，支持
> Host / Comm / Instrument / Routine 四种节点、圆角矩形、贝塞尔连线、
> 画布缩放/平移、网格背景、节点状态指示与端口类型高亮。
> Lab Engine 主界面现在有三个 Tab：
> - **运行**：原来的主界面，选择/运行测试例程。
> - **例程结构**：只读查看当前选中的测试例程的仪器依赖链，Tab 标题会显示例程名。
> - **测试系统设计**：可编辑的框图编辑器，支持新建空白例程或基于现有例程模板修改，
>   生成新的测试例程 Python 文件。
> 也可通过 `python test_setup_panel.py` 单独预览。

通信例程套件位于 `lab_engine/routines/communication/`，通过 `sys.path` 自动定位
同 workspace 下的 `DMT_PY_NN` 仓库并调用其中的 pipeline 函数。

#### 例程插件接口

一个例程就是一个普通 `.py` 文件，放在 `lab_engine/routines/` 或未来配置的用户目录中：

```python
NAME = "偏置 IV 扫描"
DESCRIPTION = "GPD CH1 提供 DUT 直流偏置，K2400 执行 IV 扫描"
ICON = "⚡"

INSTRUMENTS = {
    "k2400": {"type": "keithley2400", "required": True},
    "gpd": {"type": "gpd4303s", "required": True},
}

PARAMS = [
    {"name": "bias_v", "label": "偏置电压 (V)", "type": "float",
     "default": 3.3, "min": 0.0, "max": 32.0},
    {"name": "start_v", "label": "起始电压 (V)", "type": "float",
     "default": -1.0, "min": -200.0, "max": 200.0},
    # ...
]

def run(instruments, params, context):
    k2400 = instruments["k2400"]
    gpd = instruments["gpd"]

    context.log("开始扫描...")
    gpd.set_voltage(1, params["bias_v"])
    gpd.output_on()

    for v, i in scan_loop(k2400, params):
        context.point(voltage=v, current=i)
        if context.is_stopped():
            break

    context.done(success=True)
```

`context` 提供：

- `context.log(text, level="info")`：写入日志面板
- `context.progress(current, total)`：更新进度条
- `context.point(**kwargs)`：实时数据点（自动绘图）
- `context.data(**kwargs)`：最终聚合数据
- `context.is_stopped()`：检查用户是否点击停止

---

## 项目结构

```
RS-232_lab_device-main/          # 项目根目录
├── ivlab/                       # 仪器驱动与扫描库
│   ├── core/                    # 核心基础设施
│   │   ├── exceptions.py        # 自定义异常类
│   │   ├── config.py            # ScanConfig / InstrumentConfig
│   │   └── logger.py            # 统一日志（控制台 + 文件）
│   ├── instruments/             # 仪器驱动层（只负责单点控制与查询）
│   │   ├── base.py              # BaseInstrument 抽象基类（RS-232）
│   │   ├── scpi_mixin.py        # SCPI 指令集 Mixin
│   │   ├── scpi_instrument.py   # SCPI 协议适配器（RS-232）
│   │   ├── gpib_instrument.py   # GPIB 协议适配器（pyvisa）
│   │   ├── tsp_instrument.py    # TSP/Lua 协议适配器
│   │   ├── keithley2400.py      # 2400 RS-232 实现
│   │   ├── keithley2400_gpib.py # 2400 GPIB/NI488 实现
│   │   ├── keithley2450.py      # 2450 兼容模式
│   │   ├── keithley2600.py      # 2600B TSP 模式
│   │   ├── optical_power_meter.py  # 2359-R 预留
│   │   ├── monochromator.py     # CS260 RS-232 ASCII 协议
│   │   ├── cornerstone260.py    # CS260 USB（Newport DLL 桥接）
│   │   ├── usbtmc_instrument.py # USB-TMC 协议适配器（pyvisa + NI-VISA）
│   │   ├── sva1032x.py          # Siglent SVA1032X 频谱/矢网分析仪（USB-TMC）
│   │   ├── gpd4303s.py          # GW Instek GPD-4303S 直流电源（USB-B 虚拟串口）
│   │   └── _cornerstone_bridge.ps1  # 32 位 PowerShell 通信桥
│   ├── scanner/                 # 扫描与分析引擎（上层编排逻辑）
│   │   ├── iv_scanner.py        # IV 扫描引擎
│   │   ├── wavelength_scanner.py# 波长扫描引擎
│   │   ├── hysteresis.py        # 回滞分析器
│   │   ├── multi_instrument.py  # 多仪器协调器
│   │   └── data_handler.py      # CSV / JSON 数据保存
│   └── utils/
│       └── port_scanner.py      # COM 口自动扫描
├── lab_engine/                  # 通用实验室仪器引擎（Phase 1）
│   ├── app.py                   # LabEngineApp 主窗口
│   ├── __main__.py              # python -m lab_engine
│   ├── core/                    # 引擎核心
│   │   ├── registry.py          # InstrumentRegistry / RoutineRegistry
│   │   ├── setup_graph.py       # Setup 框图数据模型（Node / Edge / JSON）
│   │   ├── routine_context.py   # 例程运行时上下文
│   │   └── data_manager.py      # run_id / CSV / JSON 保存
│   ├── gui/                     # GUI 组件
│   │   ├── shell.py             # DPI / 主题 / 字体
│   │   ├── connection_panel.py  # 自动仪器连接面板
│   │   ├── routine_panel.py     # 例程参数面板
│   │   ├── setup_panel.py       # Setup 框图节点编辑器
│   │   ├── plot_panel.py        # 实时曲线
│   │   └── log_panel.py         # 日志面板
│   ├── instruments/             # 仪器注册（复用 ivlab 驱动 + DMT_PY_NN 适配器）
│   │   ├── __init__.py          # 注册 K2400 / GPD4303S / CS260 / SVA1032X / M8190A / 示波器
│   │   ├── m8190a.py            # M8190A AWG 适配器
│   │   └── oscilloscope.py      # Keysight 示波器适配器
│   └── routines/                # 内置例程插件
│       ├── basic_iv_scan.py     # 基础 IV 扫描
│       ├── bias_iv_sweep.py     # GPD 偏置 + K2400 IV 扫描
│       ├── hysteresis_scan.py   # 回滞扫描分析
│       ├── mono_iv_scan.py      # 单色仪 + 源表联动
│       ├── sva1032x_vna.py      # SVA1032X VNA 测量
│       ├── wavelength_scan.py   # 波长扫描
│       └── communication/       # 通信例程套件
│           ├── grid_scan.py     # DMT 参数网格扫描
│           ├── dmt_pipeline.py  # DMT 完整流程
│           └── nn_equalize.py   # NN 后均衡
├── examples/                    # 示例脚本（可直接运行）
│   ├── basic_iv_scan.py         # 基础扫描示例
│   ├── hysteresis_scan.py       # 回滞分析示例
│   ├── wavelength_scan.py       # CS260 波长扫描示例
│   ├── multi_device_demo.py     # 多仪器协调示例
│   ├── sva1032x_demo.py         # SVA1032X 频谱仪示例
│   ├── gpd4303s_demo.py         # GPD-4303S 电源 USB-B 示例
│   ├── gpd4303s_gui.py          # GPD-4303S 图形化监控面板
│   ├── k2400_gpd4303s_routine_gui.py  # K2400 + GPD4303S 联合测试例程 GUI（旧原型）
│   └── routines/                # 可导入的测试例程插件目录（旧原型）
│       └── bias_iv_sweep.py     # 示例：GPD 偏置 + K2400 IV 扫描
│   └── setups/                  # Setup 框图示例
│       └── bias_iv_setup.labsetup.json
├── lab_engine_app.py            # 引擎启动入口
├── README.md
├── CHANGELOG.md
└── requirements.txt
```

层次约定：`instruments` 驱动层只提供单点移动/查询；扫描序列等编排逻辑
统一放在 `scanner` 层，避免下层模块反向依赖上层。

---

## 核心类说明

### BaseInstrument（抽象基类）

所有仪器的统一接口：

```python
inst.connect()          # 连接（支持重试）
inst.disconnect()       # 断开（自动关闭输出）
inst.write(cmd)         # 发送指令
inst.read()             # 读取响应
inst.query(cmd)         # 发送并读取
inst.reset()            # 仪器复位
inst.idn()              # 查询型号

# 子类必须实现：
inst.set_source_mode("voltage")   # 或 "current"；切换后自动测量互补物理量：
                                  #   电压源测电流、电流源测电压（:SENS:FUNC 自动下发），
                                  #   set_measure_function 不允许设成与源模式相同的物理量
inst.set_compliance(0.1)          # 限值（对端物理量：电压源限电流、电流源限电压）
inst.set_nplc(1.0)                # 积分时间
inst.set_output_level(1.0)        # 设置输出
inst.measure()                    # 返回 {voltage, current, resistance, timestamp}
inst.output_on() / output_off()   # 输出开关
inst.set_range(auto=True)         # 量程设置
```

### IVScanner（扫描引擎）

```python
from ivlab.core.config import ScanConfig
from ivlab.scanner.iv_scanner import IVScanner

config = ScanConfig(
    start_v=0.0, stop_v=2.0, points=101,
    nplc=1.0, compliance_i=0.1,
    scan_type="double",      # single / double / sweep
    n_average=3,             # 平均次数
    randomize_direction=True # 随机化方向
)

scanner = IVScanner(instrument, config)
results = scanner.run()      # 执行扫描
avg = scanner.get_averaged_result()  # 获取平均结果
```

### HysteresisAnalyzer（回滞分析）

```python
from ivlab.scanner.hysteresis import HysteresisAnalyzer

analyzer = HysteresisAnalyzer()
h = analyzer.analyze(forward_result, backward_result)

print(f"回滞面积: {h.hysteresis_area:.3e}")
print(f"回滞指数: {h.hysteresis_index:.4f}")
print(f"最大 ΔI:  {h.delta_i_max:.3e} A")
```

### Cornerstone260（单色仪 USB 接口）与波长扫描

CS260 的 USB 版不是虚拟串口，需通过 Newport 官方 `Cornerstone.dll` 通信。
该 DLL 是 .NET 2.0 程序集，在 64 位进程下枚举设备会触发 `IntPtr` 溢出，
因此驱动内部启动一个 32 位 Windows PowerShell 子进程加载 DLL
（`_cornerstone_bridge.ps1`），主进程通过 JSON 行协议与其通信。

**前提**：必须先在 Windows 上安装 **Newport Mono Utility**（例如 5.0.4 版本，
含 Cypress USB 驱动）。DLL 默认搜索路径为
`C:\Program Files (x86)\Newport\Mono Utility 5.0.4\Cornerstone DLL\`；
若安装路径不同，可在代码或 Lab Engine 面板中显式指定 `dll_path`。

```python
from ivlab.instruments.cornerstone260 import Cornerstone260
from ivlab.scanner.wavelength_scanner import WavelengthScanner, WavelengthScanConfig
from ivlab.scanner.data_handler import DataHandler

mono = Cornerstone260()          # 或 Cornerstone260(dll_path=r"...")
mono.connect()
print(mono.idn())                # Cornerstone 260, SN1003, V04.40
print(mono.get_wavelength())     # 当前波长 (nm)

config = WavelengthScanConfig(
    start_nm=400.0, stop_nm=700.0, step_nm=1.0,
    scan_type="double",           # 往返扫描
)
scanner = WavelengthScanner(mono, config)   # 可传 power_meter= 同步读功率
results = scanner.run()

handler = DataHandler(output_dir="./data")
handler.save_wavelength_scan(results)
mono.disconnect()
```

RS-232 接口的 CS260 直接使用 `ivlab.instruments.monochromator.Monochromator(port="COMx")`，
ASCII 指令以 `\r` 终止，`goto_wavelength()` 轮询 `WAVE?` 判定到位。

### SVA1032X（频谱/矢量网络分析仪，USB-TMC）

SVA1032X 的 USB-B Device 口是 **USB-TMC 设备**（不是虚拟串口），
需安装 NI-VISA（或 Keysight VISA），经 pyvisa 访问。
运行示例：`python examples/sva1032x_demo.py`（VNA 模式）或 `--mode sa`（频谱模式）。

```python
from ivlab.instruments.sva1032x import SVA1032X

sva = SVA1032X()              # 按 Siglent VID (0xF4EC) 自动发现；也可传 resource_name
sva.connect()
print(sva.idn())

# VNA 模式：S 参数测量
sva.set_mode("vna")
sva.set_vna_parameter("S21")               # S11 / S21
sva.set_vna_format("mlog")                 # 对数幅度
sva.set_frequency(start=1e6, stop=3.2e9)   # 扫频范围（也支持 center/span）
sva.set_sweep_points(1601)
sva.set_amplitude(ref_level=0, scale_per_div=10)  # 参考电平 / Scale-Div
sva.set_reference_position(5)              # 参考点位置 0~10 格（VNA）

sva.single_sweep()
sva.set_marker(1, True)
sva.set_marker_mode(1, "delta")            # normal / delta / fixed(SA) / off
sva.set_marker_position(1, 2.4e9)          # Marker 位置
sva.set_marker_reference(1, 2)             # Delta 参考点 = Marker2（SA: Relative-To）
sva.set_reference_marker(True)             # VNA 参考 Marker R
print(sva.get_marker(1))                   # {'x': Hz, 'y': dB}
sva.disconnect()

# SA 模式：频谱分析
sva.set_mode("sa")
sva.set_frequency(center=2.4e9, span=100e6)
sva.set_amplitude(ref_level=-20, scale_per_div=5)   # 单位 dBm
sva.set_marker_peak_track(1, True)                  # 峰值跟踪
```

### MultiInstrumentCoordinator（多仪器协调）

```python
from ivlab.scanner.multi_instrument import MultiInstrumentCoordinator, ScanStep

coord = MultiInstrumentCoordinator()
coord.add_instrument("source", keithley2400)
coord.add_instrument("mono", monochromator)
coord.add_instrument("power", power_meter)

sequence = [
    ScanStep("mono", "set_wavelength", {"wavelength": 500}, wait_after=1.0),
    ScanStep("source", "set_voltage", {"voltage": 1.0}, wait_after=0.5),
    ScanStep("power", "read_power", {"read_all": True}),
]

coord.connect_all()
data = coord.run_sequence(sequence)
coord.disconnect_all()
```

---

## 联合测试例程插件接口

`examples/k2400_gpd4303s_routine_gui.py` 支持动态加载用户编写的 Python 例程。
例程文件需暴露以下接口：

```python
NAME = "例程名称"
DESCRIPTION = "例程说明"
PARAMS = [
    {"name": "bias_v", "label": "偏置电压 (V)", "type": "float",
     "default": 3.3, "min": 0.0, "max": 32.0},
    {"name": "points", "label": "扫描点数", "type": "int",
     "default": 51, "min": 2, "max": 10001},
    {"name": "scan_type", "label": "扫描类型", "type": "choice",
     "choices": ["single", "double", "sweep"], "default": "single"},
    {"name": "enable", "label": "启用某功能", "type": "bool", "default": True},
]

def run(instruments, params, report):
    k2400 = instruments["k2400"]   # Keithley2400 实例
    gpd = instruments["gpd"]       # GPD4303S 实例

    report("log", text="开始测试")
    report("progress", current=1, total=10)
    report("point", voltage=0.0, current=1e-6)

    if report("is_stopped"):       # 检查用户是否请求停止
        return
```

支持的参数类型：`float` / `int` / `choice` / `bool`。GUI 会根据 `PARAMS`
动态生成输入面板，运行结果自动保存到 `data/k2400_gpd_<timestamp>/` 目录。

---

## GPIB / NI488 使用说明

Keithley 2400 除 RS-232 外，也支持通过 GPIB（IEEE-488）控制。

### 前提

1. 安装 VISA 后端（任选其一）：
   - **NI-VISA**：National Instruments 官方驱动，配合 NI GPIB-USB-HS 卡
   - **Keysight VISA**：配合 Keysight 82357B 等 GPIB-USB 适配器
   - **pyvisa-py**：纯 Python 后端，无需安装大体积驱动（功能有限）

2. 确认 pyvisa 能识别到仪器：

```python
import pyvisa
rm = pyvisa.ResourceManager()
print(rm.list_resources())
# 应输出类似：('GPIB0::22::INSTR',)
```

### 代码示例

```python
from ivlab.instruments.keithley2400_gpib import Keithley2400GPIB

inst = Keithley2400GPIB(gpib_addr=22)
inst.connect()
print(inst.idn())
inst.output_on()
print(inst.measure())
inst.disconnect()
```

### 命令行示例

```bash
python examples/basic_iv_scan.py --gpib 22
```

---

## 扩展新仪器

以 Newport 2359-R 为例，只需在预留接口中补全协议：

```python
# ivlab/instruments/optical_power_meter.py

def measure(self) -> dict:
    self.write("READ?")  # 替换为实际指令
    resp = self.read()
    return {
        "power": float(resp),
        "unit": "dBm",
        "timestamp": time.time()
    }
```

扫描引擎和协调器会自动识别，**无需修改上层代码**。

---

## 仪器通信协议速查

### Keithley 2400 / 2450（SCPI）

```
*RST                    # 复位
:SOUR:FUNC VOLT        # 电压源
:SENS:FUNC "CURR"      # 测电流
:SENS:CURR:PROT 0.1    # 电流合规 100mA
:SENS:CURR:NPLC 1      # NPLC
:OUTP ON               # 开启输出
:READ?                 # 读取 V,I,R,time
:OUTP OFF              # 关闭输出
```

### Keithley 2600B（TSP / Lua）

```lua
reset()
smua.source.func = smua.OUTPUT_DCVOLTS
smua.source.levelv = 1.0
smua.source.limiti = 0.1
smua.measure.nplc = 1
smua.source.output = smua.OUTPUT_ON
print(smua.measure.v())   -- 电压
print(smua.measure.i())   -- 电流
smua.source.output = smua.OUTPUT_OFF
```

### Cornerstone 260（ASCII）

```
WAVE 500.0     # 设置波长 500nm
WAVE?          # 查询波长
SHUTTER O      # 打开快门
SHUTTER C      # 关闭快门
GRAT 2         # 切换到 2 号光栅
FILTER 3       # 切换到 3 号滤光片
```

USB 接口经 Newport DLL 调用同一 ASCII 指令集（`sendCommand`/`getResponse`）。

### Siglent SVA1032X（SCPI，USB-TMC）

```
:INSTrument:SELect SA|VNA              # 模式切换（频谱 / 矢量网络分析）
:FREQuency:STARt|STOP|CENTer|SPAN      # 扫频范围（SA/VNA 通用）
:SWEep:POINts 1601                     # 扫描点数
:DISPlay:WINDow:TRACe:Y:SCALe:RLEVel -20      # 参考电平 (SA, dBm)
:DISPlay:WINDow1:TRACe1:Y:SCALe:RLEVel 0      # 参考电平 (VNA, dB)
:DISPlay:WINDow1:TRACe1:Y:SCALe:PDIVision 10  # Scale/Div
:DISPlay:WINDow1:TRACe1:Y:SCALe:RPOSition 5    # 参考点位置 0~10 (VNA)
:CALCulate1:PARameter1:DEFine S11|S21  # VNA 测量参数
:CALCulate:MARKer1:STATe ON            # Marker 开关
:CALCulate:MARKer1:MODE POSition|DELTa|FIXed|OFF   # Marker 模式
:CALCulate:MARKer1:X 2.4 GHz           # Marker 位置
:CALCulate:MARKer1:Y?                  # Marker 读数
:CALCulate:MARKer1:RELative:TO:MARKer 2   # Delta 参考 Marker (SA)
:CALCulate:MARKer:REFerence:STATe ON   # 参考 Marker R (VNA)
:INITiate1:IMMediate                   # 单次扫描 (VNA)
:TRACe:DATA? 1                         # 读取迹线数据
```

### GW Instek GPD-4303S（USB-B 虚拟串口）

默认串口参数：9600/8/N/1，无流控；上电后需先发 `REMOTE` 进入远程模式。

```
REMOTE             # 进入远程控制模式
*IDN?              # 读取型号
VSET1:5.000        # 设置 CH1 电压 5V
ISET1:0.200        # 设置 CH1 电流 0.2A
VOUT1?             # 读取 CH1 实际输出电压
IOUT1?             # 读取 CH1 实际输出电流
OUT1               # 打开总输出
OUT0               # 关闭总输出
STATUS?            # 读取状态（前 4 位通常对应 CH1~CH4 的 CV/CC）
LOCAL              # 返回本地控制
```

---

## 调试与日志

- 所有 SCPI/TSP 指令和仪器响应自动记录到 `logs/ivlab.log`
- 开启原始通信打印：`inst._debug = True`
- Ctrl+C 安全退出：自动关闭输出、切回本地、保存已采数据
- 溢出检测：自动识别 `9.91E37` 并标记为 `NaN`

---

## 数据格式

### CSV 文件结构

```csv
# IV Scan Result
# Direction,forward
# nplc,1.0
# compliance,0.1

Voltage(V),Current(A),Resistance(Ohm),Time(s)
0.000000e+00,1.234567e-06,8.100000e+05,0.000000
0.020000e+00,2.345678e-06,4.200000e+05,0.050000
...
```

### 回滞分析 CSV

```csv
# Hysteresis Analysis
# Hysteresis Area,1.234e-08
# Hysteresis Index,0.0234

Voltage(V),Forward_I(A),Backward_I(A),Delta_I(A)
```

---

## 作者

**zengyi-xu** — 集成光子器件与光计算系统研究

---

## License

MIT
