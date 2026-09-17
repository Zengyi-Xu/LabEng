"""DMT 低代码节点库。


把 DMT_PY_NN 中的通信算法封装成可拖拽的功能节点，每个节点：
- 输入端口：接收上游节点传递过来的变量
- 输出端口：把计算结果传递给下游节点
- 参数：在属性面板中设置（对应函数的关键字参数）


节点函数签名统一为 func(inputs, params, ctx) -> dict，
inputs/返回值均以端口名称为键。算法实现直接复用 dmt_core / utils /
virtual_channel / nn_equalizer 中的函数，保证与 main.py 流程一致。
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


import numpy as np


from . import config
from .dmt_core import (
    qam_modulate,
    qam_demodulate,
    load_constellation,
    load_snr_table,
    assign_qam_order_from_snr,
    bit_loading_hh,
    bit_loading_lc,
    create_pilot_mask,
    insert_pilots,
    estimate_channel_from_pilots,
    phase_recovery_from_pilots,
    phase_recovery,
    smooth,
    generate_preemphasis_weights,
    generate_dmt_tx,
    generate_qpsk_tx,
    generate_bitloading_tx,
    dmt_receiver,
    estimate_snr_per_carrier,
    ber_est_by_snr,
)
from .utils import (
    load_txt,
    save_txt,
    load_mat,
    save_mat,
    add_dummy,
    center_normalize,
    apply_hardware_preEQ,
    sync_waveform,
    plot_time_waveform,
    plot_spectrum,
    plot_constellation,
    plot_snrs,
    plot_dmt_spectrogram,
    plot_tx_rx_nonlinearity,
    plot_bit_power_loading,
    plot_ser_ber_per_carrier,
    plot_constellation_density,
    plot_constellation_by_order,
)
from .virtual_channel import VirtualChannel




# ----------------------------------------------------------------------
# 节点定义结构
# ----------------------------------------------------------------------
@dataclass
class PortDef:
    name: str
    label: str
    data_type: str = "any"
    required: bool = True   # 仅对输入端口有意义




@dataclass
class ParamDef:
    name: str
    label: str
    type: str = "str"       # float | int | str | bool | choice
    default: Any = ""
    choices: List[str] = field(default_factory=list)
    minimum: Optional[float] = None
    maximum: Optional[float] = None




@dataclass
class NodeDef:
    type_id: str
    label: str
    category: str
    description: str
    inputs: List[PortDef]
    outputs: List[PortDef]
    params: List[ParamDef]
    func: Optional[Callable[[Dict[str, Any], Dict[str, Any], Any], Dict[str, Any]]]




# 节点类别配色（供编辑器使用）
CATEGORY_COLORS = {
    "数据源":   "#3B82F6",
    "预编码":   "#8B5CF6",
    "调制":     "#06B6D4",
    "预均衡":   "#10B981",
    "信道":     "#F59E0B",
    "后均衡":   "#DB2777",
    "解调":     "#0891B2",
    "分析":     "#EA580C",
    "画图":     "#65A30D",
    "变量存取": "#475569",
    "硬件":     "#B45309",
    "标注":     "#94A3B8",
}


NODES: Dict[str, NodeDef] = {}




def register(node_def: NodeDef) -> NodeDef:
    NODES[node_def.type_id] = node_def
    return node_def




def get_node_def(type_id: str) -> Optional[NodeDef]:
    return NODES.get(type_id)




def node_types_by_category() -> Dict[str, List[NodeDef]]:
    out: Dict[str, List[NodeDef]] = {}
    for nd in NODES.values():
        out.setdefault(nd.category, []).append(nd)
    return out




# ----------------------------------------------------------------------
# 小工具
# ----------------------------------------------------------------------
def _complex_from_str(value: Any, default: complex) -> complex:
    try:
        return complex(str(value).strip())
    except (ValueError, TypeError):
        return default




def _out_path(ctx, filename: str) -> Path:
    """把相对文件名解析到本次运行目录。"""
    p = Path(filename)
    if p.is_absolute():
        return p
    return Path(ctx.run_dir) / p




def _plot_show(params: Dict[str, Any]) -> bool:
    return bool(params.get("show", False))




# ======================================================================
# 数据源
# ======================================================================
def _fn_const(inputs, params, ctx):
    """常量节点：把文本解析为 Python 数值/数组。"""
    text = str(params.get("value", "0"))
    try:
        value = eval(text, {"__builtins__": {}}, {"np": np})  # noqa: S307
    except Exception as exc:
        raise ValueError(f"常量表达式无法解析: {text!r} ({exc})")
    ctx.log(f"常量 = {value!r}")
    return {"value": value}




def _fn_bit_source(inputs, params, ctx):
    """生成随机比特，并按 RQ 把比特流编码为十进制符号编号（与 generate_dmt_tx 一致）。"""
    rq = inputs.get("RQ_in")
    datano = int(params.get("datano", config.DATANO_BPL))
    seed = int(params.get("seed", config.RANDOM_SEED))


    if rq is not None:
        rq = np.asarray(rq).ravel().astype(int)
        carrierno1 = len(rq)
        max_bits = int(rq.max()) if rq.size else 1
    else:
        carrierno1 = int(params.get("carrierno1", config.CARRIERNO1))
        bits = int(params.get("bits", 2))
        rq = np.full(carrierno1, bits, dtype=int)
        max_bits = bits


    rng = np.random.default_rng(seed)
    b2data = rng.integers(0, 2, size=(carrierno1, max_bits * datano))
    origin_dec_data = np.zeros((carrierno1, datano), dtype=int)
    for n in range(carrierno1):
        b = int(rq[n])
        if b <= 0:
            continue
        bits_stream = b2data[n, :b * datano]
        data_2 = bits_stream.reshape(datano, b)
        weights = 2 ** np.arange(b)[::-1]      # MSB first
        origin_dec_data[n, :] = np.dot(data_2, weights).astype(int)


    ctx.log(f"比特源: {carrierno1} 子载波 x {datano} 符号, seed={seed}")
    return {"dec": origin_dec_data, "binary": b2data, "RQ": rq}




def _fn_load_var(inputs, params, ctx):
    """从文件读取变量（txt / npy / mat）。"""
    path = Path(str(params.get("path", "")))
    if not str(path):
        raise ValueError("请在参数中填写文件路径")
    if not path.is_absolute():
        path = config.BASE_DIR / path
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    fmt = params.get("format", "auto")
    if fmt == "auto":
        fmt = path.suffix.lstrip(".").lower()
    if fmt == "txt":
        value = load_txt(path)
    elif fmt == "npy":
        value = np.load(path, allow_pickle=True)
    elif fmt == "mat":
        d = load_mat(path)
        key = str(params.get("key", "")).strip()
        value = d[key] if key else d
    else:
        raise ValueError(f"不支持的格式: {fmt}")
    arr = np.asarray(value) if not isinstance(value, dict) else None
    ctx.log(f"读取变量 <- {path}"
            + (f" shape={arr.shape} dtype={arr.dtype}" if arr is not None else ""))
    return {"value": value}




def _fn_load_rx_file(inputs, params, ctx):
    """读取示波器 RX 波形文件；路径留空时自动取 rxdata 目录下最新的 rawOSC_*.txt。"""
    path_str = str(params.get("path", "")).strip()
    if path_str:
        path = Path(path_str)
        if not path.is_absolute():
            path = config.BASE_DIR / path
    else:
        matches = sorted(config.RXDATA_DIR.glob("rawOSC_*.txt"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        if not matches:
            raise FileNotFoundError(f"{config.RXDATA_DIR} 下没有 rawOSC_*.txt 文件")
        path = matches[0]
    rx = load_txt(path)
    ctx.log(f"读取 RX 波形 <- {path} (len={len(rx)})")
    return {"waveform": rx}




# ======================================================================
# 预编码（比特加载 / 导频）
# ======================================================================
def _fn_bit_loading(inputs, params, ctx):
    """比特/功率分配（HH + 简化 Levin-Campello），与 generate_bitloading_tx 一致。"""
    snrs = np.asarray(inputs["snrs"]).ravel()
    constellation = params.get("constellation", config.CONSTELLATION_QAM)
    ratio = int(params.get("ratio", config.RATIO))
    b_max = int(params.get("b_max", 10))


    table_path = params.get("snr_table", "")
    if str(table_path).strip():
        snr_table = load_snr_table(Path(str(table_path)))
    elif constellation == config.CONSTELLATION_APSK:
        snr_table = load_snr_table(config.SNR_TABLE_APSK5)
    else:
        snr_table = load_snr_table(config.SNR_TABLE_FEC4)


    qam_order_all = assign_qam_order_from_snr(snrs, snr_table, b_max=b_max)
    _, _, raise_num = bit_loading_hh(snrs, qam_order_all, snr_table)
    se_add = raise_num - ratio
    S, RQ = bit_loading_lc(snrs, qam_order_all, snr_table, SE_add=se_add, b_max=b_max)


    # comb 导频时导频子载波置零（与 generate_bitloading_tx 一致）
    pattern = params.get("pilot_pattern", config.PILOT_PATTERN)
    if pattern == "comb":
        carrierno1 = len(snrs)
        datano = int(params.get("datano", config.DATANO_BPL))
        pmask = create_pilot_mask(
            carrierno1, datano, pattern="comb",
            comb_start=int(params.get("comb_start", config.PILOT_COMB_START)),
            comb_spacing=int(params.get("comb_spacing", config.PILOT_COMB_SPACING)),
        )
        pilot_sc = np.where(pmask[:, 0])[0]
        RQ[pilot_sc] = 0
        S[pilot_sc] = 1.0
        ctx.log(f"Comb 导频：{len(pilot_sc)} 个子载波置零")


    carrierno1 = len(snrs)
    datarate = (RQ.mean() * config.AWG_SAMPLE_RATE / config.UPSAMPLENO
                * (carrierno1 / config.CARRIERNO) / 1e9)
    ctx.log(f"比特加载: 平均 {RQ.mean():.4f} bit/符号, 估计速率 {datarate:.4f} Gbps")
    return {"RQ": RQ, "S": S, "datarate": float(datarate), "snr_table": snr_table}




def _fn_pilot_insert(inputs, params, ctx):
    """在时频网格上插入导频（training_only / comb / mesh）。"""
    qamdata = np.asarray(inputs["symbols_in"])
    carrierno1, datano = qamdata.shape
    pattern = params.get("pattern", config.PILOT_PATTERN)
    mask = create_pilot_mask(
        carrierno1, datano, pattern,
        comb_start=int(params.get("comb_start", config.PILOT_COMB_START)),
        comb_spacing=int(params.get("comb_spacing", config.PILOT_COMB_SPACING)),
        mesh_start_freq=int(params.get("mesh_start_freq", config.PILOT_MESH_START_FREQ)),
        mesh_freq_spacing=int(params.get("mesh_freq_spacing", config.PILOT_MESH_FREQ_SPACING)),
        mesh_start_time=int(params.get("mesh_start_time", config.PILOT_MESH_START_TIME)),
        mesh_time_spacing=int(params.get("mesh_time_spacing", config.PILOT_MESH_TIME_SPACING)),
    )
    pilot_value = _complex_from_str(params.get("pilot_value", str(config.PILOT_VALUE)),
                                    config.PILOT_VALUE)
    avt = inputs.get("AVT_in")
    if avt is None:
        avt = np.ones((carrierno1, datano))
    dec = inputs.get("dec_in")
    if dec is None:
        dec = np.zeros((carrierno1, datano), dtype=int)
    qamdata, avt, dec = insert_pilots(qamdata, np.asarray(avt, dtype=float),
                                      np.asarray(dec), mask, pilot_value)
    ctx.log(f"导频插入: pattern={pattern}, 导频数={int(mask.sum())}")
    return {"symbols": qamdata, "AVT": avt, "dec": dec, "mask": mask}




# ======================================================================
# 调制
# ======================================================================
def _fn_qam_mod(inputs, params, ctx):
    """QAM/APSK 星座映射 + 按 S 做功率分配 + 归一化（与 generate_dmt_tx 一致）。"""
    dec = np.asarray(inputs["dec"])
    carrierno1, datano = dec.shape
    rq = inputs.get("RQ_in")
    if rq is None:
        bits = int(params.get("bits", 2))
        rq = np.full(carrierno1, bits, dtype=int)
    else:
        rq = np.asarray(rq).ravel().astype(int)
    S = inputs.get("S")
    S = np.ones(carrierno1) if S is None else np.asarray(S, dtype=float).ravel()
    constellation = params.get("constellation", config.CONSTELLATION_QAM)
    normalize_flag = int(params.get("normalize_flag", config.NORMALIZE_FLAG))


    qamdata = np.zeros((carrierno1, datano), dtype=complex)
    avt = np.zeros((carrierno1, datano))
    for n in range(carrierno1):
        bits = int(rq[n])
        order = 2 ** bits if bits > 0 else 1
        if order == 1:
            avt[n, :] = 1.0
            continue
        sym = qam_modulate(dec[n, :], order, constellation)
        qamdata[n, :] = sym
        if normalize_flag == 1:
            all_cons = load_constellation(order, constellation)
            avg_pow = np.sqrt(np.mean(np.abs(all_cons) ** 2))
            avt[n, :] = avg_pow / S[n]
        else:
            avt[n, :] = np.max(np.abs(sym)) / S[n]
        qamdata[n, :] = qamdata[n, :] / avt[n, :]


    ctx.log(f"QAM 调制: {constellation}, 阶数 {int(rq.min())}~{int(rq.max())} bit")
    return {"symbols": qamdata, "AVT": avt, "RQ": rq}




def _fn_dmt_mod(inputs, params, ctx):
    """DMT 帧组装：Hermitian 共轭对称 -> 上采样 -> IFFT -> 加 CP -> 串行化。"""
    qamdata = np.asarray(inputs["symbols"])
    carrierno1, datano = qamdata.shape
    carrierno = int(params.get("carrierno", config.CARRIERNO))
    zeropad1 = int(params.get("zeropad1", config.ZEROPAD1))
    upsampleno = int(params.get("upsampleno", config.UPSAMPLENO))
    cp = int(params.get("cp", config.CP))
    if carrierno // 2 - zeropad1 != carrierno1:
        ctx.log(f"[WARN] carrierno/2-zeropad1={carrierno // 2 - zeropad1} "
                f"与输入符号数 {carrierno1} 不一致", level="warning")


    data_final = np.zeros((carrierno, datano), dtype=complex)
    data_final[zeropad1:carrierno // 2, :] = qamdata
    data_final[carrierno // 2 + 1:carrierno - zeropad1 + 1, :] = np.conj(np.flipud(qamdata))


    dataiq_upsample = np.zeros((carrierno * upsampleno, datano), dtype=complex)
    dataiq_upsample[:carrierno // 2, :] = data_final[:carrierno // 2, :]
    dataiq_upsample[-carrierno // 2:, :] = data_final[carrierno // 2:, :]


    dataifft = np.fft.ifft(dataiq_upsample, axis=0)
    dataifft1 = np.vstack([dataifft[-cp * upsampleno:, :], dataifft])
    ifft_stream = np.real(dataifft1.reshape(-1, order="F").copy())


    ref_waveform = center_normalize(ifft_stream)          # 无 dummy，用作同步参考
    tx_waveform, dummy = add_dummy(ifft_stream, base=64)
    tx_waveform = center_normalize(tx_waveform)


    ctx.log(f"DMT 调制: 波形长度={len(tx_waveform)}, dummy={len(dummy)}")
    return {
        "waveform": tx_waveform,
        "ref_waveform": ref_waveform,
        "ifft_stream": ifft_stream,
        "dummy_len": int(len(dummy)),
        "data_final": data_final,
    }




def _fn_qpsk_tx(inputs, params, ctx):
    """粗粒度：QPSK 探测发射（直接调用 generate_qpsk_tx）。"""
    datano = int(params.get("datano", config.DATANO_QPSK))
    tx_dict = generate_qpsk_tx(datano=datano)
    waveform = (tx_dict["tx_waveform_pre"] if tx_dict.get("tx_waveform_pre") is not None
                else tx_dict["tx_waveform"])
    ctx.log(f"QPSK 探测 TX: datano={datano}, 波形长度={len(waveform)}")
    return {"tx_dict": tx_dict, "waveform": waveform}




def _fn_dmt_tx_full(inputs, params, ctx):
    """粗粒度：完整 DMT 发射（直接调用 generate_dmt_tx / generate_bitloading_tx）。"""
    datano = int(params.get("datano", config.DATANO_BPL))
    constellation = params.get("constellation", config.CONSTELLATION_QAM)
    snrs = inputs.get("snrs")
    rq = inputs.get("RQ")
    if snrs is not None:
        tx_dict = generate_bitloading_tx(np.asarray(snrs).ravel(),
                                         constellation=constellation,
                                         datano=datano)
    elif rq is not None:
        S = inputs.get("S")
        S = np.ones_like(np.asarray(rq).ravel()) if S is None else np.asarray(S, dtype=float).ravel()
        tx_dict = generate_dmt_tx(np.asarray(rq).ravel(), S, datano, constellation)
    else:
        raise ValueError("DMT 完整发射节点需要连接 snrs 或 RQ 输入")
    waveform = (tx_dict["tx_waveform_pre"] if tx_dict.get("tx_waveform_pre") is not None
                else tx_dict["tx_waveform"])
    ctx.log(f"DMT 完整发射: 波形长度={len(waveform)}")
    return {"tx_dict": tx_dict, "waveform": waveform}




# ======================================================================
# 预均衡
# ======================================================================
def _fn_preeq_weights(inputs, params, ctx):
    """生成预均衡幅度权重（port of MATLAB Pre.m，method 0~5）。"""
    channel_mag = inputs.get("channel_mag")
    method = int(params.get("method", config.PRE_METHOD))
    save_path = _out_path(ctx, str(params.get("save_path", "th7.txt")))
    weights = generate_preemphasis_weights(
        channel_mag=channel_mag,
        method=method,
        equal_db=float(params.get("equal_db", config.PRE_EQUAL_DB)),
        equal_db2=float(params.get("equal_db2", config.PRE_EQUAL_DB2)),
        n_subcarriers=int(params.get("n_subcarriers", config.CARRIERNO1)),
        save_path=save_path,
    )
    ctx.log(f"预均衡权重: method={method}, N={len(weights)}, 保存到 {save_path}")
    return {"weights": weights, "path": str(save_path)}




def _fn_apply_preeq(inputs, params, ctx):
    """对 IFFT 串行流应用硬件预均衡（th7.txt），再加 dummy + 归一化。"""
    stream = np.asarray(inputs["ifft_stream"]).ravel()
    th7_str = str(params.get("th7_file", "")).strip()
    th7_path = Path(th7_str) if th7_str else config.TH7_FILE
    if not th7_path.is_absolute():
        th7_path = config.BASE_DIR / th7_path
    fsamp = float(params.get("fsamp", config.AWG_SAMPLE_RATE))
    upsampleno = int(params.get("upsampleno", config.UPSAMPLENO))
    if not th7_path.exists():
        ctx.log(f"{th7_path} 不存在，按 method={config.PRE_METHOD} 自动生成", level="warning")
        generate_preemphasis_weights(n_subcarriers=int(params.get("n_subcarriers", config.CARRIERNO1)),
                                     save_path=th7_path)
    data_pre = apply_hardware_preEQ(stream, fsamp, upsampleno, th7_path)
    data_pre, dummy = add_dummy(data_pre, base=64)
    data_pre = center_normalize(data_pre)
    data_pre = data_pre / np.sqrt(np.mean(np.abs(data_pre) ** 2))
    ctx.log(f"硬件预均衡: 输出长度={len(data_pre)}")
    return {"waveform": data_pre, "dummy_len": int(len(dummy))}




# ======================================================================
# 信道
# ======================================================================
def _fn_virtual_channel(inputs, params, ctx):
    """虚拟信道：低通 + AWGN + 三阶非线性 + 延迟。"""
    x = np.asarray(inputs["waveform_in"]).ravel()
    ch = VirtualChannel(
        fs=float(params.get("fs", config.AWG_SAMPLE_RATE)),
        fc=float(params.get("fc", config.VIRTUAL_CHANNEL_FC)),
        snr_db=float(params.get("snr_db", config.VIRTUAL_CHANNEL_SNR_DB)),
        nonlin_coeff=float(params.get("nonlin_coeff", config.VIRTUAL_CHANNEL_NONLINEARITY)),
        delay=int(params.get("delay", config.VIRTUAL_CHANNEL_DELAY)),
        attenuation=float(params.get("attenuation", config.VIRTUAL_CHANNEL_ATTENUATION)),
    )
    rx = ch.apply(x)
    ctx.log(f"虚拟信道: SNR={ch.snr_db} dB, fc={ch.fc / 1e9:.2f} GHz, "
            f"输入 {len(x)} -> 输出 {len(rx)}")
    return {"waveform": rx}




def _fn_awg_download(inputs, params, ctx):
    """把波形下载到 M8190A AWG（需要硬件连接）。"""
    from awg_download import download_to_awg, parse_tcpip_visa
    x = np.asarray(inputs["waveform_in"]).ravel()
    addr = str(params.get("visa_addr", config.M8190A_VISA_ADDR))
    host, port = parse_tcpip_visa(addr)
    download_to_awg(x,
                    fs=float(params.get("fs", config.AWG_SAMPLE_RATE)),
                    vpp=float(params.get("vpp", config.AWG_VPP)),
                    host=host, port=port,
                    route=params.get("route", config.AWG_OUTPUT_ROUTE))
    ctx.log(f"AWG 下载完成: {len(x)} 点 -> {addr}")
    return {"waveform": x}




def _fn_scope_capture(inputs, params, ctx):
    """从 Keysight 示波器采集波形（需要硬件连接）。"""
    from oscilloscope import KeysightScopeUSB
    addr = str(params.get("visa_addr", config.OSC_VISA_ADDR))
    channel = params.get("channel", config.OSC_CHANNEL)
    sample_rate = float(params.get("sample_rate", config.OSC_SAMPLE_RATE))
    timebase = float(params.get("timebase_scale", 80e-6))
    ctx.log(f"示波器采集中: {addr} {channel} ...")
    with KeysightScopeUSB(resource=addr) as scope:
        rx, _ = scope.capture(channel=channel, sample_rate=sample_rate,
                              timebase_scale=timebase, resample_to_awg=True)
    ctx.log(f"示波器采集完成: {len(rx)} 点")
    return {"waveform": rx}




# ======================================================================
# 后均衡
# ======================================================================
def _fn_nn_posteq(inputs, params, ctx):
    """NN 后均衡（ZY_BiGRU_GPU 子进程）。"""
    from .nn_equalizer import run_nn_equalizer
    tx = np.asarray(inputs["tx_waveform"]).ravel()
    rx = np.asarray(inputs["rx_waveform"]).ravel()
    ctx.log("运行 NN 后均衡（可能需要较长时间）...")
    out = run_nn_equalizer(tx, rx)
    ctx.log(f"NN 后均衡完成: 输出长度={len(out)}")
    return {"waveform": np.asarray(out).ravel()}




# ======================================================================
# 解调
# ======================================================================
def _fn_sync(inputs, params, ctx):
    """互相关符号同步，截取与 TX 等长的 RX 片段。"""
    rx = np.asarray(inputs["rx"]).ravel()
    tx = np.asarray(inputs["tx"]).ravel()
    h = int(params.get("h", 1))
    rx_sync = sync_waveform(rx, tx, h=h)
    ctx.log(f"同步: 输出长度={len(rx_sync)}")
    return {"waveform": rx_sync}




def _fn_dmt_demod(inputs, params, ctx):
    """DMT 解帧：去 dummy -> 整形为符号矩阵 -> 去 CP -> FFT -> 取有效子载波。"""
    rx = np.asarray(inputs["waveform"]).ravel()
    carrierno = int(params.get("carrierno", config.CARRIERNO))
    zeropad1 = int(params.get("zeropad1", config.ZEROPAD1))
    upsampleno = int(params.get("upsampleno", config.UPSAMPLENO))
    cp = int(params.get("cp", config.CP))
    datano = int(params["datano"])
    dummy_len = inputs.get("dummy_len")
    dummy_len = int(dummy_len) if dummy_len is not None else int(params.get("dummy_len", 0))
    if dummy_len > 0:
        rx = rx[:-dummy_len]


    sym_len = (carrierno + cp) * upsampleno
    data_rx = rx[:sym_len * datano].reshape(sym_len, datano, order="F")
    rv_tifft = data_rx[cp * upsampleno:, :]
    rv_down1 = np.fft.fft(rv_tifft, axis=0)
    rv_down = rv_down1[zeropad1:carrierno // 2, :]
    ctx.log(f"DMT 解帧: 符号矩阵 {rv_down.shape[0]} 子载波 x {rv_down.shape[1]} 符号")
    return {"symbols": rv_down}




def _fn_channel_eq(inputs, params, ctx):
    """信道估计 + 迫零均衡 + 相位恢复（导频或 training symbol，与 dmt_receiver 一致）。"""
    out = np.asarray(inputs["rx_symbols"])
    in_ref = np.asarray(inputs["tx_symbols"])
    carrierno1, datano = out.shape
    trainingno = int(params.get("trainingno", config.TRAININGNO))
    rq = inputs.get("RQ")
    mask = inputs.get("mask")
    avt = inputs.get("AVT")
    avt = np.ones((carrierno1, datano)) if avt is None else np.asarray(avt, dtype=float)


    if rq is not None:
        rq_arr = np.asarray(rq).ravel()
        active_carrier = np.zeros(carrierno1, dtype=bool)
        ncopy = min(carrierno1, rq_arr.size)
        active_carrier[:ncopy] = rq_arr[:ncopy] > 0
    else:
        active_carrier = np.any(np.abs(in_ref) > 1e-12, axis=1)


    use_pilots = mask is not None and np.asarray(mask).any()
    if use_pilots:
        mask = np.asarray(mask, dtype=bool)
        H = estimate_channel_from_pilots(out, in_ref, mask)
        out2 = out * H
        rx_recovery, phase = phase_recovery_from_pilots(out2, in_ref, mask)
        ha = np.mean(H, axis=1)
        ctx.log("信道估计: 导频辅助")
    else:
        # training symbol 信道估计（安全除法 + 频率平滑，与 dmt_receiver 一致）
        tx_train = in_ref[:, :trainingno]
        rx_train = out[:, :trainingno]
        h1 = np.full(tx_train.shape, np.nan + 1j * np.nan, dtype=complex)
        valid_div = (
            active_carrier[:, None]
            & (np.abs(tx_train) > 1e-12)
            & (np.abs(rx_train) > 1e-12)
            & np.isfinite(tx_train.real) & np.isfinite(tx_train.imag)
            & np.isfinite(rx_train.real) & np.isfinite(rx_train.imag)
        )
        np.divide(tx_train, rx_train, out=h1, where=valid_div)


        finite_h1 = np.isfinite(h1.real) & np.isfinite(h1.imag)
        count_h1 = np.sum(finite_h1, axis=1)
        ha_raw = np.full(carrierno1, np.nan + 1j * np.nan, dtype=complex)
        good_rows = count_h1 > 0
        if np.any(good_rows):
            h1_zeroed = np.where(finite_h1, h1, 0.0 + 0.0j)
            ha_raw[good_rows] = (np.sum(h1_zeroed[good_rows], axis=1)
                                 / count_h1[good_rows])


        valid_h = active_carrier & np.isfinite(ha_raw.real) & np.isfinite(ha_raw.imag)
        valid_idx = np.flatnonzero(valid_h)
        carrier_idx = np.arange(carrierno1)
        if valid_idx.size >= 2:
            ha_fill = (np.interp(carrier_idx, valid_idx, ha_raw[valid_idx].real)
                       + 1j * np.interp(carrier_idx, valid_idx, ha_raw[valid_idx].imag))
        elif valid_idx.size == 1:
            ha_fill = np.full(carrierno1, ha_raw[valid_idx[0]], dtype=complex)
        else:
            ha_fill = np.ones(carrierno1, dtype=complex)


        ha = smooth(ha_fill, window_len=7)
        H = np.tile(ha, (datano, 1)).T
        out2 = out * H
        rx_recovery, phase = phase_recovery(out2, in_ref, carrierno1, datano, start=50)
        ctx.log("信道估计: training symbol")


    eq_symbols = rx_recovery * avt
    tx_ref = in_ref * avt
    return {
        "eq_symbols": eq_symbols,
        "tx_ref": tx_ref,
        "channel": ha,
        "phase": phase,
    }




def _fn_qam_demod(inputs, params, ctx):
    """最小欧氏距离硬判决解调。"""
    sig = np.asarray(inputs["symbols"])
    carrierno1, datano = sig.shape
    rq = inputs.get("RQ_in")
    if rq is None:
        bits = int(params.get("bits", 2))
        rq = np.full(carrierno1, bits, dtype=int)
    else:
        rq = np.asarray(rq).ravel().astype(int)
    constellation = params.get("constellation", config.CONSTELLATION_QAM)


    dec = np.zeros((carrierno1, datano), dtype=int)
    for n in range(carrierno1):
        bits = int(rq[n])
        if bits < 1:
            continue
        dec[n, :] = qam_demodulate(sig[n, :], 2 ** bits, constellation)
    ctx.log(f"QAM 解调: {constellation}, 阶数 {int(rq.min())}~{int(rq.max())} bit")
    return {"dec": dec, "RQ": rq}




def _fn_dmt_rx_full(inputs, params, ctx):
    """粗粒度：完整 DMT 接收（直接调用 dmt_receiver）。"""
    rx = np.asarray(inputs["waveform"]).ravel()
    tx_dict = inputs["tx_dict"]
    res = dmt_receiver(rx, tx_dict)
    ctx.log(f"DMT 接收: BER={res['ber']:.4e}, SER={res['ser']:.4e}")
    return {
        "result": res,
        "eq_symbols": res["out2"],
        "tx_ref": res["in_ref"],
        "snr": res["SNR_R"],
        "ber": float(res["ber"]),
        "ser": float(res["ser"]),
        "channel": res["channel_response"],
        "mask": res["pilot_mask"],
    }




# ======================================================================
# 分析（解码 / SNR / BER）
# ======================================================================
def _fn_snr_calc(inputs, params, ctx):
    """逐子载波 SNR = mean(|Tx|^2)/mean(|Rx-Tx|^2)（与 dmt_receiver 一致）。"""
    in_denorm = np.asarray(inputs["tx_ref"])
    out2_denorm = np.asarray(inputs["rx_symbols"])
    carrierno1, datano = in_denorm.shape
    rq = inputs.get("RQ")
    mask = inputs.get("mask")
    mask = (np.zeros((carrierno1, datano), dtype=bool)
            if mask is None else np.asarray(mask, dtype=bool))


    if rq is not None:
        rq_arr = np.asarray(rq).ravel()
        active_carrier = np.zeros(carrierno1, dtype=bool)
        ncopy = min(carrierno1, rq_arr.size)
        active_carrier[:ncopy] = rq_arr[:ncopy] > 0
    else:
        active_carrier = np.any(np.abs(in_denorm) > 1e-12, axis=1)


    snr_r = np.full(carrierno1, np.nan, dtype=float)
    for n in range(carrierno1):
        if not active_carrier[n]:
            continue
        valid = ~mask[n, :]
        valid &= (np.isfinite(in_denorm[n, :].real) & np.isfinite(in_denorm[n, :].imag)
                  & np.isfinite(out2_denorm[n, :].real) & np.isfinite(out2_denorm[n, :].imag))
        if not np.any(valid):
            continue
        sig_pow = float(np.mean(np.abs(in_denorm[n, valid]) ** 2))
        err_pow = float(np.mean(np.abs(out2_denorm[n, valid] - in_denorm[n, valid]) ** 2))
        if not np.isfinite(sig_pow) or sig_pow <= 1e-15:
            continue
        if not np.isfinite(err_pow) or err_pow <= 1e-15:
            continue
        snr_r[n] = sig_pow / err_pow


    valid_snr_idx = np.where(active_carrier & np.isfinite(snr_r) & (snr_r > 0))[0]
    missing_active_idx = np.where(active_carrier & ~np.isfinite(snr_r))[0]
    if len(valid_snr_idx) > 0:
        for n in missing_active_idx:
            nearest = valid_snr_idx[np.argmin(np.abs(valid_snr_idx - n))]
            snr_r[n] = snr_r[nearest]


    mean_snr = float(np.nanmean(snr_r[valid_snr_idx])) if len(valid_snr_idx) else np.nan
    mean_db = 10 * np.log10(mean_snr) if np.isfinite(mean_snr) and mean_snr > 0 else np.nan
    ctx.log(f"SNR 估计: 平均 {mean_db:.2f} dB（{len(valid_snr_idx)} 个有效子载波）")
    return {"snr": snr_r, "mean_snr_db": mean_db}




def _fn_ber_calc(inputs, params, ctx):
    """对比发送/接收十进制符号，统计 BER / SER（跳过 RQ=0 与导频位置）。"""
    tx_dec = np.asarray(inputs["tx_dec"])
    rx_dec = np.asarray(inputs["rx_dec"])
    carrierno1, datano = tx_dec.shape
    rq = inputs.get("RQ")
    mask = inputs.get("mask")
    mask = (np.zeros((carrierno1, datano), dtype=bool)
            if mask is None else np.asarray(mask, dtype=bool))


    bit_errors_total = 0
    bits_total = 0
    symbol_errors_total = 0
    symbols_total = 0
    ber_per_carrier = np.zeros(carrierno1)
    ser_per_carrier = np.zeros(carrierno1)
    bits_per_carrier = np.zeros(carrierno1, dtype=int)


    for n in range(carrierno1):
        if rq is not None:
            bits = int(np.asarray(rq).ravel()[n])
        else:
            max_symbol = int(np.max(tx_dec[n, :]))
            bits = int(np.ceil(np.log2(max_symbol + 1))) if max_symbol > 0 else 0
        bits_per_carrier[n] = bits
        if bits < 1:
            continue
        valid = ~mask[n, :]
        n_valid = int(np.sum(valid))
        if n_valid == 0:
            continue
        tx_v = tx_dec[n, valid].astype(np.uint16)
        rx_v = rx_dec[n, valid].astype(np.uint16)


        err_sym = int(np.count_nonzero(rx_v != tx_v))
        ser_per_carrier[n] = err_sym / n_valid
        symbol_errors_total += err_sym
        symbols_total += n_valid


        diff = np.bitwise_xor(rx_v, tx_v)
        bit_errs = 0
        for k in range(bits):
            bit_errs += int(np.count_nonzero(diff & np.uint16(1 << k)))
        ber_per_carrier[n] = bit_errs / (n_valid * bits)
        bit_errors_total += bit_errs
        bits_total += bits * n_valid


    ber = bit_errors_total / bits_total if bits_total > 0 else 0.0
    ser = symbol_errors_total / symbols_total if symbols_total > 0 else 0.0
    ctx.log(f"误码统计: BER={ber:.6e}, SER={ser:.6e} ({bits_total} bits)")
    return {
        "ber": float(ber),
        "ser": float(ser),
        "ber_per_carrier": ber_per_carrier,
        "ser_per_carrier": ser_per_carrier,
        "bits_per_carrier": bits_per_carrier,
    }




def _fn_ber_est(inputs, params, ctx):
    """由 SNR 理论估计 BER（ber_est_by_snr）。"""
    snr = np.asarray(inputs["snr"], dtype=float).ravel()
    order = int(params.get("order", 16))
    mean_snr = float(np.nanmean(snr))
    ber = ber_est_by_snr(mean_snr, order)
    ctx.log(f"理论 BER (SNR={10 * np.log10(mean_snr):.2f} dB, {order}-QAM): {ber:.4e}")
    return {"ber": float(ber)}




# ======================================================================
# 画图
# ======================================================================
def _make_plot_func(kind: str):
    """生成画图节点函数；图像统一保存到运行目录的 PNG。"""
    def _func(inputs, params, ctx):
        title = str(params.get("title", kind))
        show = _plot_show(params)
        out = _out_path(ctx, f"{params.get('filename', kind)}.png")


        if kind == "plot_time":
            sig = np.asarray(inputs["waveform"]).ravel()
            plot_time_waveform(np.arange(len(sig)), sig, title, out=out, show=show)
        elif kind == "plot_spectrum":
            sig = np.asarray(inputs["waveform"]).ravel()
            fs = float(params.get("fs", config.AWG_SAMPLE_RATE))
            plot_spectrum(sig, fs, title, out=out, show=show)
        elif kind == "plot_spectrogram":
            sig = np.asarray(inputs["waveform"]).ravel()
            fs = float(params.get("fs", config.AWG_SAMPLE_RATE))
            plot_dmt_spectrogram(sig, fs, title, out=out, show=show)
        elif kind == "plot_constellation":
            iq = np.asarray(inputs["symbols"]).ravel()
            plot_constellation(iq, title, out=out, show=show)
        elif kind == "plot_snr":
            est = np.asarray(inputs["snr"]).ravel()
            real = inputs.get("snr_real")
            real = est if real is None else np.asarray(real).ravel()
            plot_snrs(est, real, out=out, show=show)
        elif kind == "plot_nonlinearity":
            tx = np.asarray(inputs["tx"]).ravel()
            rx = np.asarray(inputs["rx"]).ravel()
            plot_tx_rx_nonlinearity(tx, rx, out=out, show=show)
        elif kind == "plot_bitloading":
            snrs = np.asarray(inputs["snrs"]).ravel()
            rq = np.asarray(inputs["RQ"]).ravel()
            S = np.asarray(inputs["S"]).ravel()
            snrs_db = 10 * np.log10(np.maximum(np.nan_to_num(snrs), 1e-12))
            plot_bit_power_loading(np.arange(len(rq)), snrs_db, rq, S,
                                   ratio=int(params.get("ratio", config.RATIO)),
                                   rate_gbps=float(params.get("rate_gbps", 0.0)),
                                   out=out, show=show)
        elif kind == "plot_ser_ber":
            ser = np.asarray(inputs["ser"]).ravel()
            ber = np.asarray(inputs["ber"]).ravel()
            rq = inputs.get("RQ")
            plot_ser_ber_per_carrier(ser, ber,
                                     RQ=None if rq is None else np.asarray(rq).ravel(),
                                     out=out, show=show)
        elif kind in ("plot_const_density", "plot_const_order"):
            out2 = np.asarray(inputs["eq_symbols"])
            in_ref = np.asarray(inputs["tx_ref"])
            rq = np.asarray(inputs["RQ"]).ravel()
            mask = inputs.get("mask")
            fn = (plot_constellation_density if kind == "plot_const_density"
                  else plot_constellation_by_order)
            fn(out2, in_ref, rq, pilot_mask=mask, out=out, show=show)
        else:
            raise ValueError(f"未知画图类型: {kind}")
        ctx.log(f"图像已保存: {out}")
        return {"path": str(out)}
    return _func




# ======================================================================
# 变量存取
# ======================================================================
def _fn_save_var(inputs, params, ctx):
    """把变量保存到文件（txt / npy / mat）。"""
    value = inputs["value"]
    filename = str(params.get("filename", "variable.npy"))
    fmt = params.get("format", "auto")
    if fmt == "auto":
        fmt = Path(filename).suffix.lstrip(".").lower() or "npy"
    out = _out_path(ctx, filename)
    out.parent.mkdir(parents=True, exist_ok=True)


    if fmt == "txt":
        arr = np.atleast_1d(np.asarray(value))
        if np.iscomplexobj(arr):
            flat = arr.ravel()
            np.savetxt(out, np.column_stack([flat.real, flat.imag]), fmt="%.6f")
        else:
            save_txt(out, arr)
    elif fmt == "npy":
        np.save(out, value)
    elif fmt == "mat":
        key = str(params.get("key", "data")).strip() or "data"
        save_mat(out, **{key: value})
    else:
        raise ValueError(f"不支持的格式: {fmt}")
    ctx.log(f"变量已保存 -> {out}")
    return {"path": str(out)}




def _fn_print_var(inputs, params, ctx):
    """查看变量内容：弹窗显示形状/类型/统计信息（不刷运行日志）。"""
    value = inputs["value"]
    name = str(params.get("name", "value"))
    if isinstance(value, np.ndarray):
        finite = np.asarray(value)[np.isfinite(np.real(value))] if value.size else value
        stats = ""
        if np.asarray(value).size and np.issubdtype(value.dtype, np.number):
            stats = (f"\nmin={np.min(finite):.4g}, max={np.max(finite):.4g}, "
                     f"mean={np.mean(finite):.4g}")
        text = f"{name}: ndarray shape={value.shape} dtype={value.dtype}{stats}"
    elif isinstance(value, dict):
        text = f"{name}: dict keys={list(value.keys())}"
    else:
        text = f"{name}: {type(value).__name__} = {value!r}"
    ctx.popup(f"打印变量: {name}", text)
    return {"value_out": value}




def _fn_note(inputs, params, ctx):
    return {}




# ======================================================================
# 节点注册
# ======================================================================
_COMMON_DMT_PARAMS = [
    ParamDef("carrierno", "子载波总数", "int", config.CARRIERNO),
    ParamDef("zeropad1", "零填充", "int", config.ZEROPAD1),
    ParamDef("upsampleno", "上采样倍数", "int", config.UPSAMPLENO),
    ParamDef("cp", "CP 长度", "int", config.CP),
]




def _register_all():
    # ---------------- 数据源 ----------------
    register(NodeDef(
        "const", "常量", "数据源",
        "常量数值或 numpy 表达式（如 np.ones(512)）。",
        [], [PortDef("value", "值", "any")],
        [ParamDef("value", "表达式", "str", "0")],
        _fn_const,
    ))
    register(NodeDef(
        "bit_source", "比特源", "数据源",
        "生成随机比特并编码为十进制符号编号（连接 RQ 时按比特加载分配编码）。",
        [PortDef("RQ_in", "比特分配", "rq", required=False)],
        [PortDef("dec", "十进制符号", "dec"),
         PortDef("binary", "比特矩阵", "bits"),
         PortDef("RQ", "比特分配", "rq")],
        [ParamDef("datano", "符号数", "int", config.DATANO_BPL),
         ParamDef("bits", "每载波比特数", "int", 2),
         ParamDef("carrierno1", "有效子载波数", "int", config.CARRIERNO1),
         ParamDef("seed", "随机种子", "int", config.RANDOM_SEED)],
        _fn_bit_source,
    ))
    register(NodeDef(
        "load_var", "读取变量", "数据源",
        "从 txt / npy / mat 文件读取变量（相对路径基于项目根目录）。",
        [], [PortDef("value", "值", "any")],
        [ParamDef("path", "文件路径", "str", ""),
         ParamDef("format", "格式", "choice", "auto", ["auto", "txt", "npy", "mat"]),
         ParamDef("key", "MAT 键名", "str", "")],
        _fn_load_var,
    ))
    register(NodeDef(
        "load_rx_file", "读取RX波形", "数据源",
        "读取示波器 RX 波形文件；路径留空时自动取 rxdata 下最新的 rawOSC_*.txt。",
        [], [PortDef("waveform", "RX 波形", "waveform")],
        [ParamDef("path", "文件路径", "str", "")],
        _fn_load_rx_file,
    ))


    # ---------------- 预编码 ----------------
    register(NodeDef(
        "bit_loading", "比特加载", "预编码",
        "HH + 简化 Levin-Campello 比特/功率分配（输入为逐子载波 SNR 线性值）。",
        [PortDef("snrs", "SNR", "snr")],
        [PortDef("RQ", "比特分配", "rq"),
         PortDef("S", "功率分配", "power"),
         PortDef("datarate", "估计速率", "scalar", ),
         PortDef("snr_table", "SNR 表", "array")],
        [ParamDef("constellation", "星座", "choice", config.CONSTELLATION_QAM,
                  [config.CONSTELLATION_QAM, config.CONSTELLATION_APSK]),
         ParamDef("ratio", "rate 调整量", "int", config.RATIO),
         ParamDef("b_max", "最大阶数", "int", 10),
         ParamDef("snr_table", "SNR 表路径", "str", ""),
         ParamDef("pilot_pattern", "导频图案", "choice", config.PILOT_PATTERN,
                  ["training_only", "comb", "mesh"]),
         ParamDef("datano", "符号数", "int", config.DATANO_BPL)],
        _fn_bit_loading,
    ))
    register(NodeDef(
        "pilot_insert", "导频插入", "预编码",
        "按 comb / mesh 图案在时频网格插入导频。",
        [PortDef("symbols_in", "星座符号", "symbols"),
         PortDef("AVT_in", "归一化因子", "avt", required=False),
         PortDef("dec_in", "十进制符号", "dec", required=False)],
        [PortDef("symbols", "星座符号", "symbols"),
         PortDef("AVT", "归一化因子", "avt"),
         PortDef("dec", "十进制符号", "dec"),
         PortDef("mask", "导频掩码", "mask")],
        [ParamDef("pattern", "图案", "choice", config.PILOT_PATTERN,
                  ["training_only", "comb", "mesh"]),
         ParamDef("pilot_value", "导频值", "str", str(config.PILOT_VALUE)),
         ParamDef("comb_start", "梳状起始", "int", config.PILOT_COMB_START),
         ParamDef("comb_spacing", "梳状间隔", "int", config.PILOT_COMB_SPACING),
         ParamDef("mesh_start_freq", "网状起始频率", "int", config.PILOT_MESH_START_FREQ),
         ParamDef("mesh_freq_spacing", "网状频率间隔", "int", config.PILOT_MESH_FREQ_SPACING),
         ParamDef("mesh_start_time", "网状起始符号", "int", config.PILOT_MESH_START_TIME),
         ParamDef("mesh_time_spacing", "网状符号间隔", "int", config.PILOT_MESH_TIME_SPACING)],
        _fn_pilot_insert,
    ))


    # ---------------- 调制 ----------------
    register(NodeDef(
        "qam_mod", "QAM 调制", "调制",
        "QAM/APSK 星座映射 + 功率分配 + 归一化（逐子载波按 RQ 决定阶数）。",
        [PortDef("dec", "十进制符号", "dec"),
         PortDef("RQ_in", "比特分配", "rq", required=False),
         PortDef("S", "功率分配", "power", required=False)],
        [PortDef("symbols", "星座符号", "symbols"),
         PortDef("AVT", "归一化因子", "avt"),
         PortDef("RQ", "比特分配", "rq")],
        [ParamDef("bits", "每载波比特数", "int", 2),
         ParamDef("constellation", "星座", "choice", config.CONSTELLATION_QAM,
                  [config.CONSTELLATION_QAM, config.CONSTELLATION_APSK]),
         ParamDef("normalize_flag", "归一化方式", "choice", str(config.NORMALIZE_FLAG),
                  ["0", "1"])],
        _fn_qam_mod,
    ))
    register(NodeDef(
        "dmt_mod", "DMT 调制", "调制",
        "Hermitian 共轭对称 -> 上采样 -> IFFT -> 加 CP -> 串行化。",
        [PortDef("symbols", "星座符号", "symbols")],
        [PortDef("waveform", "TX 波形", "waveform"),
         PortDef("ref_waveform", "参考波形", "waveform"),
         PortDef("ifft_stream", "IFFT 流", "waveform"),
         PortDef("dummy_len", "dummy 长度", "scalar"),
         PortDef("data_final", "频域帧", "symbols")],
        list(_COMMON_DMT_PARAMS),
        _fn_dmt_mod,
    ))
    register(NodeDef(
        "qpsk_tx", "QPSK 探测发射", "调制",
        "粗粒度节点：完整 QPSK 信道探测发射（调用 generate_qpsk_tx）。",
        [],
        [PortDef("tx_dict", "TX 字典", "dict"),
         PortDef("waveform", "TX 波形", "waveform")],
        [ParamDef("datano", "符号数", "int", config.DATANO_QPSK)],
        _fn_qpsk_tx,
    ))
    register(NodeDef(
        "dmt_tx_full", "DMT 完整发射", "调制",
        "粗粒度节点：连接 snrs 走 bitloading 发射，连接 RQ/S 直接按分配发射。",
        [PortDef("snrs", "SNR", "snr", required=False),
         PortDef("RQ", "比特分配", "rq", required=False),
         PortDef("S", "功率分配", "power", required=False)],
        [PortDef("tx_dict", "TX 字典", "dict"),
         PortDef("waveform", "TX 波形", "waveform")],
        [ParamDef("datano", "符号数", "int", config.DATANO_BPL),
         ParamDef("constellation", "星座", "choice", config.CONSTELLATION_QAM,
                  [config.CONSTELLATION_QAM, config.CONSTELLATION_APSK])],
        _fn_dmt_tx_full,
    ))


    # ---------------- 预均衡 ----------------
    register(NodeDef(
        "preeq_weights", "预均衡权重", "预均衡",
        "生成每子载波预均衡幅度权重（method 0~5，port of MATLAB Pre.m）。",
        [PortDef("channel_mag", "信道幅度", "array", required=False)],
        [PortDef("weights", "权重", "array"),
         PortDef("path", "保存路径", "scalar")],
        [ParamDef("method", "方法", "choice", str(config.PRE_METHOD),
                  ["0", "1", "2", "3", "4", "5"]),
         ParamDef("equal_db", "门限 (dB)", "float", config.PRE_EQUAL_DB),
         ParamDef("equal_db2", "第二门限", "float", config.PRE_EQUAL_DB2),
         ParamDef("n_subcarriers", "子载波数", "int", config.CARRIERNO1),
         ParamDef("save_path", "保存路径", "str", "th7.txt")],
        _fn_preeq_weights,
    ))
    register(NodeDef(
        "apply_preeq", "应用预均衡", "预均衡",
        "对 IFFT 串行流应用 th7.txt 硬件预均衡，再加 dummy + 归一化。",
        [PortDef("ifft_stream", "IFFT 流", "waveform")],
        [PortDef("waveform", "TX 波形", "waveform"),
         PortDef("dummy_len", "dummy 长度", "scalar")],
        [ParamDef("th7_file", "th7 路径", "str", ""),
         ParamDef("fsamp", "采样率 (Hz)", "float", config.AWG_SAMPLE_RATE),
         ParamDef("upsampleno", "上采样倍数", "int", config.UPSAMPLENO),
         ParamDef("n_subcarriers", "子载波数", "int", config.CARRIERNO1)],
        _fn_apply_preeq,
    ))


    # ---------------- 信道 ----------------
    register(NodeDef(
        "virtual_channel", "虚拟信道", "信道",
        "一阶低通 + AWGN + 三阶非线性 + 延迟（无仪器时仿真信道）。",
        [PortDef("waveform_in", "TX 波形", "waveform")],
        [PortDef("waveform", "RX 波形", "waveform")],
        [ParamDef("fs", "采样率 (Hz)", "float", config.AWG_SAMPLE_RATE),
         ParamDef("fc", "截止频率 (Hz)", "float", config.VIRTUAL_CHANNEL_FC),
         ParamDef("snr_db", "SNR (dB)", "float", config.VIRTUAL_CHANNEL_SNR_DB),
         ParamDef("nonlin_coeff", "非线性系数", "float", config.VIRTUAL_CHANNEL_NONLINEARITY),
         ParamDef("delay", "延迟 (样点)", "int", config.VIRTUAL_CHANNEL_DELAY),
         ParamDef("attenuation", "衰减", "float", config.VIRTUAL_CHANNEL_ATTENUATION)],
        _fn_virtual_channel,
    ))
    register(NodeDef(
        "awg_download", "AWG 下载", "硬件",
        "把波形下载到 M8190A AWG（需要硬件连接）。",
        [PortDef("waveform_in", "TX 波形", "waveform")],
        [PortDef("waveform", "TX 波形", "waveform")],
        [ParamDef("visa_addr", "VISA 地址", "str", config.M8190A_VISA_ADDR),
         ParamDef("fs", "采样率 (Hz)", "float", config.AWG_SAMPLE_RATE),
         ParamDef("vpp", "幅度 (Vpp)", "float", config.AWG_VPP),
         ParamDef("route", "输出路径", "choice", config.AWG_OUTPUT_ROUTE,
                  ["DC", "AC", "DAC"])],
        _fn_awg_download,
    ))
    register(NodeDef(
        "scope_capture", "示波器采集", "硬件",
        "从 Keysight 示波器采集波形（需要硬件连接）。",
        [],
        [PortDef("waveform", "RX 波形", "waveform")],
        [ParamDef("visa_addr", "VISA 地址", "str", config.OSC_VISA_ADDR),
         ParamDef("channel", "通道", "choice", config.OSC_CHANNEL,
                  ["CHAN1", "CHAN2", "CHAN3", "CHAN4"]),
         ParamDef("sample_rate", "采样率 (Hz)", "float", config.OSC_SAMPLE_RATE),
         ParamDef("timebase_scale", "时基 (s/div)", "float", 80e-6)],
        _fn_scope_capture,
    ))


    # ---------------- 后均衡 ----------------
    register(NodeDef(
        "nn_posteq", "NN 后均衡", "后均衡",
        "ZY_BiGRU_GPU 神经网络后均衡（子进程运行，耗时较长）。",
        [PortDef("tx_waveform", "TX 波形", "waveform"),
         PortDef("rx_waveform", "RX 波形", "waveform")],
        [PortDef("waveform", "均衡后波形", "waveform")],
        [],
        _fn_nn_posteq,
    ))


    # ---------------- 解调 ----------------
    register(NodeDef(
        "sync", "波形同步", "解调",
        "互相关符号同步，截取与 TX 等长的 RX 片段。",
        [PortDef("rx", "RX 波形", "waveform"),
         PortDef("tx", "TX 参考", "waveform")],
        [PortDef("waveform", "同步波形", "waveform")],
        [ParamDef("h", "偏移修正", "int", 1)],
        _fn_sync,
    ))
    register(NodeDef(
        "dmt_demod", "DMT 解帧", "解调",
        "去 dummy -> 整形 -> 去 CP -> FFT -> 取有效子载波。",
        [PortDef("waveform", "RX 波形", "waveform"),
         PortDef("dummy_len", "dummy 长度", "scalar", required=False)],
        [PortDef("symbols", "频域符号", "symbols")],
        [ParamDef("datano", "符号数", "int", config.DATANO_BPL),
         ParamDef("dummy_len", "dummy 长度", "int", 0)]
        + list(_COMMON_DMT_PARAMS),
        _fn_dmt_demod,
    ))
    register(NodeDef(
        "channel_eq", "信道估计均衡", "解调",
        "信道估计（导频或 training）+ 迫零均衡 + 相位恢复 + 反归一化。",
        [PortDef("rx_symbols", "RX 符号", "symbols"),
         PortDef("tx_symbols", "TX 参考符号", "symbols"),
         PortDef("AVT", "归一化因子", "avt", required=False),
         PortDef("RQ", "比特分配", "rq", required=False),
         PortDef("mask", "导频掩码", "mask", required=False)],
        [PortDef("eq_symbols", "均衡符号", "symbols"),
         PortDef("tx_ref", "TX 参考", "symbols"),
         PortDef("channel", "信道响应", "channel"),
         PortDef("phase", "相位", "array")],
        [ParamDef("trainingno", "training 符号数", "int", config.TRAININGNO)],
        _fn_channel_eq,
    ))
    register(NodeDef(
        "qam_demod", "QAM 解调", "解调",
        "最小欧氏距离硬判决解调（连接 RQ 时逐子载波按阶数解调）。",
        [PortDef("symbols", "频域符号", "symbols"),
         PortDef("RQ_in", "比特分配", "rq", required=False)],
        [PortDef("dec", "十进制符号", "dec"),
         PortDef("RQ", "比特分配", "rq")],
        [ParamDef("bits", "每载波比特数", "int", 2),
         ParamDef("constellation", "星座", "choice", config.CONSTELLATION_QAM,
                  [config.CONSTELLATION_QAM, config.CONSTELLATION_APSK])],
        _fn_qam_demod,
    ))
    register(NodeDef(
        "dmt_rx_full", "DMT 完整接收", "解调",
        "粗粒度节点：完整 DMT 接收解调（调用 dmt_receiver）。",
        [PortDef("waveform", "RX 波形", "waveform"),
         PortDef("tx_dict", "TX 字典", "dict")],
        [PortDef("result", "结果字典", "dict"),
         PortDef("eq_symbols", "均衡符号", "symbols"),
         PortDef("tx_ref", "TX 参考", "symbols"),
         PortDef("snr", "SNR", "snr"),
         PortDef("ber", "BER", "scalar"),
         PortDef("ser", "SER", "scalar"),
         PortDef("channel", "信道响应", "channel"),
         PortDef("mask", "导频掩码", "mask")],
        [],
        _fn_dmt_rx_full,
    ))


    # ---------------- 分析 ----------------
    register(NodeDef(
        "snr_calc", "SNR 计算", "分析",
        "逐子载波 SNR = mean(|Tx|^2) / mean(|Rx-Tx|^2)。",
        [PortDef("tx_ref", "TX 参考", "symbols"),
         PortDef("rx_symbols", "RX 符号", "symbols"),
         PortDef("RQ", "比特分配", "rq", required=False),
         PortDef("mask", "导频掩码", "mask", required=False)],
        [PortDef("snr", "SNR", "snr"),
         PortDef("mean_snr_db", "平均 SNR (dB)", "scalar")],
        [],
        _fn_snr_calc,
    ))
    register(NodeDef(
        "ber_calc", "误码率计算", "分析",
        "对比发送/接收符号统计 BER / SER（跳过 RQ=0 与导频位置）。",
        [PortDef("tx_dec", "TX 符号", "dec"),
         PortDef("rx_dec", "RX 符号", "dec"),
         PortDef("RQ", "比特分配", "rq", required=False),
         PortDef("mask", "导频掩码", "mask", required=False)],
        [PortDef("ber", "BER", "scalar"),
         PortDef("ser", "SER", "scalar"),
         PortDef("ber_per_carrier", "BER/载波", "array"),
         PortDef("ser_per_carrier", "SER/载波", "array"),
         PortDef("bits_per_carrier", "比特/载波", "rq")],
        [],
        _fn_ber_calc,
    ))
    register(NodeDef(
        "ber_est", "BER 理论估计", "分析",
        "由平均 SNR 理论估计 BER（ber_est_by_snr）。",
        [PortDef("snr", "SNR", "snr")],
        [PortDef("ber", "BER", "scalar")],
        [ParamDef("order", "QAM 阶数", "int", 16)],
        _fn_ber_est,
    ))


    # ---------------- 画图 ----------------
    register(NodeDef(
        "plot_time", "时域波形图", "画图",
        "绘制时域波形并保存 PNG 到运行目录。",
        [PortDef("waveform", "波形", "waveform")],
        [PortDef("path", "PNG 路径", "scalar")],
        [ParamDef("title", "标题", "str", "Time Waveform"),
         ParamDef("filename", "文件名", "str", "time_waveform"),
         ParamDef("show", "弹出显示", "bool", False)],
        _make_plot_func("plot_time"),
    ))
    register(NodeDef(
        "plot_spectrum", "频谱图", "画图",
        "绘制频谱并保存 PNG 到运行目录。",
        [PortDef("waveform", "波形", "waveform")],
        [PortDef("path", "PNG 路径", "scalar")],
        [ParamDef("title", "标题", "str", "Spectrum"),
         ParamDef("filename", "文件名", "str", "spectrum"),
         ParamDef("fs", "采样率 (Hz)", "float", config.AWG_SAMPLE_RATE),
         ParamDef("show", "弹出显示", "bool", False)],
        _make_plot_func("plot_spectrum"),
    ))
    register(NodeDef(
        "plot_spectrogram", "时频谱图", "画图",
        "绘制 DMT 信号时频谱（spectrogram）。",
        [PortDef("waveform", "波形", "waveform")],
        [PortDef("path", "PNG 路径", "scalar")],
        [ParamDef("title", "标题", "str", "Spectrogram"),
         ParamDef("filename", "文件名", "str", "spectrogram"),
         ParamDef("fs", "采样率 (Hz)", "float", config.AWG_SAMPLE_RATE),
         ParamDef("show", "弹出显示", "bool", False)],
        _make_plot_func("plot_spectrogram"),
    ))
    register(NodeDef(
        "plot_constellation", "星座图", "画图",
        "绘制星座图（复数符号散点）。",
        [PortDef("symbols", "符号", "symbols")],
        [PortDef("path", "PNG 路径", "scalar")],
        [ParamDef("title", "标题", "str", "Constellation"),
         ParamDef("filename", "文件名", "str", "constellation"),
         ParamDef("show", "弹出显示", "bool", False)],
        _make_plot_func("plot_constellation"),
    ))
    register(NodeDef(
        "plot_snr", "SNR 曲线图", "画图",
        "绘制逐子载波 SNR（dB）曲线；可连两路 SNR 做对比。",
        [PortDef("snr", "SNR (估计)", "snr"),
         PortDef("snr_real", "SNR (实测)", "snr", required=False)],
        [PortDef("path", "PNG 路径", "scalar")],
        [ParamDef("title", "标题", "str", "SNR"),
         ParamDef("filename", "文件名", "str", "snr"),
         ParamDef("show", "弹出显示", "bool", False)],
        _make_plot_func("plot_snr"),
    ))
    register(NodeDef(
        "plot_nonlinearity", "非线性图", "画图",
        "TX-RX 幅值散点 / hexbin 非线性分析。",
        [PortDef("tx", "TX 波形", "waveform"),
         PortDef("rx", "RX 波形", "waveform")],
        [PortDef("path", "PNG 路径", "scalar")],
        [ParamDef("title", "标题", "str", "TX-RX Nonlinearity"),
         ParamDef("filename", "文件名", "str", "nonlinearity"),
         ParamDef("show", "弹出显示", "bool", False)],
        _make_plot_func("plot_nonlinearity"),
    ))
    register(NodeDef(
        "plot_bitloading", "比特加载图", "画图",
        "SNR + 比特分配 + 功率分配组合图。",
        [PortDef("snrs", "SNR", "snr"),
         PortDef("RQ", "比特分配", "rq"),
         PortDef("S", "功率分配", "power")],
        [PortDef("path", "PNG 路径", "scalar")],
        [ParamDef("title", "标题", "str", "Bit-Power Loading"),
         ParamDef("filename", "文件名", "str", "bit_power_loading"),
         ParamDef("ratio", "ratio", "int", config.RATIO),
         ParamDef("rate_gbps", "速率 (Gbps)", "float", 0.0),
         ParamDef("show", "弹出显示", "bool", False)],
        _make_plot_func("plot_bitloading"),
    ))
    register(NodeDef(
        "plot_ser_ber", "SER/BER 图", "画图",
        "逐子载波 SER / BER 曲线。",
        [PortDef("ser", "SER/载波", "array"),
         PortDef("ber", "BER/载波", "array"),
         PortDef("RQ", "比特分配", "rq", required=False)],
        [PortDef("path", "PNG 路径", "scalar")],
        [ParamDef("title", "标题", "str", "SER/BER per Carrier"),
         ParamDef("filename", "文件名", "str", "ser_ber_per_carrier"),
         ParamDef("show", "弹出显示", "bool", False)],
        _make_plot_func("plot_ser_ber"),
    ))
    register(NodeDef(
        "plot_const_density", "星座密度图", "画图",
        "按调制阶数分类的星座密度 hexbin 图。",
        [PortDef("eq_symbols", "均衡符号", "symbols"),
         PortDef("tx_ref", "TX 参考", "symbols"),
         PortDef("RQ", "比特分配", "rq"),
         PortDef("mask", "导频掩码", "mask", required=False)],
        [PortDef("path", "PNG 路径", "scalar")],
        [ParamDef("title", "标题", "str", "Constellation Density"),
         ParamDef("filename", "文件名", "str", "constellation_density"),
         ParamDef("show", "弹出显示", "bool", False)],
        _make_plot_func("plot_const_density"),
    ))
    register(NodeDef(
        "plot_const_order", "分阶星座图", "画图",
        "按调制阶数分类的星座散点图。",
        [PortDef("eq_symbols", "均衡符号", "symbols"),
         PortDef("tx_ref", "TX 参考", "symbols"),
         PortDef("RQ", "比特分配", "rq"),
         PortDef("mask", "导频掩码", "mask", required=False)],
        [PortDef("path", "PNG 路径", "scalar")],
        [ParamDef("title", "标题", "str", "Constellation by Order"),
         ParamDef("filename", "文件名", "str", "constellation_by_order"),
         ParamDef("show", "弹出显示", "bool", False)],
        _make_plot_func("plot_const_order"),
    ))


    # ---------------- 变量存取 ----------------
    register(NodeDef(
        "save_var", "保存变量", "变量存取",
        "把变量保存到运行目录（txt / npy / mat；相对文件名基于运行目录）。",
        [PortDef("value", "值", "any")],
        [PortDef("path", "保存路径", "scalar")],
        [ParamDef("filename", "文件名", "str", "variable.npy"),
         ParamDef("format", "格式", "choice", "auto", ["auto", "txt", "npy", "mat"]),
         ParamDef("key", "MAT 键名", "str", "data")],
        _fn_save_var,
    ))
    register(NodeDef(
        "print_var", "打印变量", "变量存取",
        "在日志中打印变量的形状 / 类型 / 统计信息。",
        [PortDef("value", "值", "any")],
        [PortDef("value_out", "值(透传)", "any")],
        [ParamDef("name", "显示名", "str", "value")],
        _fn_print_var,
    ))


    # ---------------- 标注 ----------------
    register(NodeDef(
        "note", "注释", "标注",
        "纯说明文字节点，不参与执行，用于框图标注。",
        [], [],
        [ParamDef("text", "内容", "str", "")],
        _fn_note,
    ))


    # ---------------- 分组（两级层级） ----------------
    register(NodeDef(
        "group", "分组", "分组",
        "子图容器：双击进入编辑内部流程，运行时自动展开为一层。"
        "分组无端口，内部须自包含（用「保存变量/读取变量」跨分组传数据）。",
        [], [],
        [],
        None,
    ))
    CATEGORY_COLORS["分组"] = "#6366F1"




_register_all()
