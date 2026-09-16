"""Siglent SVA1032X 频谱/矢量网络分析仪驱动（USB-TMC）

SVA1000X 系列的 USB-B Device 口为 USB-TMC 设备（非虚拟串口），
需 NI-VISA / Keysight VISA 驱动，经 pyvisa 访问。

指令集来源：SIGLENT《SVA1000X Programming Guide》(PG0703P_E02A)，
VNA 模式指令兼容 Agilent E5071C 格式。

常用指令速查：
    :INSTrument[:SELect] SA|VNA                      模式切换
    [:SENSe]:FREQuency:STARt|STOP|CENTer|SPAN       扫频范围
    :DISPlay:WINDow:TRACe:Y[:SCALe]:RLEVel          参考电平 (SA)
    :DISPlay:WINDow[ch]:TRACe[n]:Y[:SCALe]:RLEVel   参考电平 (VNA)
    :DISPlay:WINDow[ch]:TRACe[n]:Y[:SCALe]:PDIVision Scale/Div
    :DISPlay:WINDow[ch]:TRACe[n]:Y[:SCALe]:RPOSition 参考点位置 0~10 (VNA)
    :CALCulate:PARameter[n]:DEFine S11|S21          VNA 测量参数
    :CALCulate:MARKer[n]:STATe|MODE|X|Y?            Marker 控制
    :CALCulate:MARKer[n]:RELative:TO:MARKer m       Delta 参考 Marker (SA)
    :CALCulate[:SELected]:MARKer:REFerence[:STATe]  参考 Marker R (VNA)
"""
import struct
import time
from typing import Optional, Union

from ..core.exceptions import ConfigurationError, ConnectionError
from .usbtmc_instrument import USBTMCInstrument

Frequency = Union[float, str]  # float 单位 Hz，或字符串如 "1.5 GHz"


def _fmt_freq(value: Frequency) -> str:
    if isinstance(value, str):
        return value
    v = float(value)
    if v >= 1e9:
        return f"{v / 1e9:g} GHz"
    if v >= 1e6:
        return f"{v / 1e6:g} MHz"
    if v >= 1e3:
        return f"{v / 1e3:g} kHz"
    return f"{v:g} Hz"


class SVA1032X(USBTMCInstrument):
    """Siglent SVA1032X 频谱分析仪 / 矢量网络分析仪

    通过 USB-B 口（USB-TMC）控制。支持 SA（频谱）与 VNA（S 参数）两种模式：
    扫频范围、参考电平、Scale/Div、参考点位置、Marker 位置/模式/参考点设置。

    用法：
        sva = SVA1032X()            # 自动发现 Siglent USB 设备
        sva.connect()
        sva.set_mode("vna")
        sva.set_vna_parameter("S21")
        sva.set_frequency(start=1e6, stop=3.2e9)
        sva.set_amplitude(ref_level=0, scale_per_div=10)
        sva.set_marker_position(1, 2.4e9)
        print(sva.get_marker(1))
        sva.disconnect()
    """

    #: 仪器模式
    MODES = {"sa": "SA", "vna": "VNA"}
    #: VNA 测量参数（S12/S22 经反向/端口2测量，视机型固件支持）
    VNA_PARAMETERS = {"S11", "S21", "S12", "S22"}
    #: VNA 显示格式
    VNA_FORMATS = {
        "mlog": "MLOGarithmic", "phase": "PHASe", "gdelay": "GDELay",
        "slin": "SLINear", "slog": "SLOGarithmic", "scomplex": "SCOMplex",
        "smith": "SMITh", "sadmittance": "SADMittance",
        "plinear": "PLINear", "plog": "PLOGarithmic", "polar": "POLar",
        "mlin": "MLINear", "swr": "SWR",
    }
    #: 标量格式（每点一个值）
    VNA_SCALAR_FORMATS = {"mlog", "phase", "gdelay", "slin", "slog",
                          "mlin", "swr", "real", "imag"}
    #: 复数格式（每点两个值）
    VNA_COMPLEX_FORMATS = {"scomplex", "smith", "sadmittance",
                           "plinear", "plog", "polar"}
    #: Marker 模式（SA 模式含 FIXed，VNA 模式仅 POSition/DELTa/OFF）
    MARKER_MODES_SA = {"normal": "POSition", "delta": "DELTa",
                       "fixed": "FIXed", "off": "OFF"}
    MARKER_MODES_VNA = {"normal": "POSition", "delta": "DELTa", "off": "OFF"}

    def __init__(self, resource_name: Optional[str] = None,
                 vid: str = "0xF4EC", timeout: float = 10.0, logger=None):
        """vid 默认为 Siglent 厂商 ID 0xF4EC"""
        super().__init__(resource_name=resource_name, vid=vid,
                         timeout=timeout, model="SVA1032X", logger=logger)
        self._mode = "sa"

    # ------------------------------------------------------------------
    # 连接与模式
    # ------------------------------------------------------------------
    def _post_connect(self):
        idn = self.idn()
        if not idn:
            raise ConnectionError(
                f"[{self.model}] 未收到 *IDN? 响应，请检查 USB 连接与 NI-VISA 驱动")
        self.logger.info(f"[{self.model}] IDN: {idn}")

    def set_mode(self, mode: str):
        """设置仪器模式: "sa"（频谱分析）或 "vna"（矢量网络分析 S 参数）"""
        mode = mode.lower()
        if mode not in self.MODES:
            raise ConfigurationError(f"不支持的模式: {mode}，可选 {list(self.MODES)}")
        self.write(f":INSTrument:SELect {self.MODES[mode]}")
        self._mode = mode
        self.logger.info(f"[{self.model}] 模式设为 {self.MODES[mode]}")

    def get_mode(self) -> str:
        """查询当前模式，返回 "sa" / "vna" 等"""
        resp = self.query(":INSTrument:SELect?").strip().upper()
        for k, v in self.MODES.items():
            if v in resp:
                return k
        return resp.lower()

    @property
    def mode(self) -> str:
        return self._mode

    # ------------------------------------------------------------------
    # 频率 / 扫频
    # ------------------------------------------------------------------
    def set_frequency(self, start: Optional[Frequency] = None,
                      stop: Optional[Frequency] = None,
                      center: Optional[Frequency] = None,
                      span: Optional[Frequency] = None):
        """设置扫频范围（start/stop 或 center/span 二选一）

        频率可用 float（单位 Hz）或字符串（如 "100 kHz"、"1.5 GHz"）。
        """
        given = [x is not None for x in (start, stop, center, span)]
        if start is not None and stop is not None:
            self.write(f":FREQuency:STARt {_fmt_freq(start)}")
            self.write(f":FREQuency:STOP {_fmt_freq(stop)}")
        elif center is not None and span is not None:
            self.write(f":FREQuency:CENTer {_fmt_freq(center)}")
            self.write(f":FREQuency:SPAN {_fmt_freq(span)}")
        elif any(given):
            # 允许单独设置某一项（如仅 center）
            for cmd, val in (("STARt", start), ("STOP", stop),
                             ("CENTer", center), ("SPAN", span)):
                if val is not None:
                    self.write(f":FREQuency:{cmd} {_fmt_freq(val)}")
        else:
            raise ConfigurationError("set_frequency 需要至少一个频率参数")
        self.logger.debug(f"[{self.model}] 频率: {self.get_frequency()}")

    def get_frequency(self) -> dict:
        """查询当前扫频设置，返回 {"start", "stop", "center", "span"} (Hz)"""
        return {
            "start": float(self.query(":FREQuency:STARt?")),
            "stop": float(self.query(":FREQuency:STOP?")),
            "center": float(self.query(":FREQuency:CENTer?")),
            "span": float(self.query(":FREQuency:SPAN?")),
        }

    def set_sweep_points(self, points: int):
        """设置扫描点数（VNA: 1~?；SA 同样适用）"""
        self.write(f":SWEep:POINts {int(points)}")
        self.logger.debug(f"[{self.model}] 扫描点数设为 {points}")

    def get_sweep_points(self) -> int:
        return int(float(self.query(":SWEep:POINts?")))

    # ------------------------------------------------------------------
    # 幅值：参考电平 / Scale / 参考点位置
    # ------------------------------------------------------------------
    def set_amplitude(self, ref_level: Optional[float] = None,
                      scale_per_div: Optional[float] = None,
                      trace: int = 1):
        """设置幅值显示

        ref_level:   参考电平，SA 单位 dBm，VNA 单位 dB（顶格值）
        scale_per_div: 每格刻度（dB/div）
        trace:       VNA 模式下作用的迹线编号 1~4（SA 忽略）
        """
        if self._mode == "vna":
            if ref_level is not None:
                self.write(f":DISPlay:WINDow1:TRACe{trace}:Y:SCALe:RLEVel {ref_level}")
            if scale_per_div is not None:
                self.write(f":DISPlay:WINDow1:TRACe{trace}:Y:SCALe:PDIVision {scale_per_div}")
        else:
            if ref_level is not None:
                self.write(f":DISPlay:WINDow:TRACe:Y:SCALe:RLEVel {ref_level}")
            if scale_per_div is not None:
                self.write(f":DISPlay:WINDow:TRACe:Y:SCALe:PDIVision {scale_per_div}")
        self.logger.debug(
            f"[{self.model}] 幅值: ref={ref_level}, scale={scale_per_div}")

    def get_amplitude(self, trace: int = 1) -> dict:
        """查询参考电平与 Scale/Div"""
        if self._mode == "vna":
            prefix = f":DISPlay:WINDow1:TRACe{trace}:Y:SCALe"
        else:
            prefix = ":DISPlay:WINDow:TRACe:Y:SCALe"
        return {
            "ref_level": float(self.query(f"{prefix}:RLEVel?")),
            "scale_per_div": float(self.query(f"{prefix}:PDIVision?")),
        }

    def set_reference_position(self, position: int, trace: int = 1):
        """设置参考点位置（仅 VNA 模式），0~10（格），默认 5

        即屏幕上参考电平所在的分格线位置。
        """
        self._require_vna("set_reference_position")
        if not 0 <= int(position) <= 10:
            raise ConfigurationError(f"参考点位置需在 0~10 之间: {position}")
        self.write(f":DISPlay:WINDow1:TRACe{trace}:Y:SCALe:RPOSition {int(position)}")
        self.logger.debug(f"[{self.model}] 参考点位置设为 {position}")

    def get_reference_position(self, trace: int = 1) -> int:
        self._require_vna("get_reference_position")
        return int(float(self.query(
            f":DISPlay:WINDow1:TRACe{trace}:Y:SCALe:RPOSition?")))

    def auto_scale(self, trace: int = 1):
        """自动刻度（仅 VNA 模式）"""
        self._require_vna("auto_scale")
        self.write(f":DISPlay:WINDow1:TRACe{trace}:Y:SCALe:AUTO")

    # ------------------------------------------------------------------
    # VNA 测量参数与格式
    # ------------------------------------------------------------------
    def set_vna_parameter(self, param: str, trace: int = 1):
        """设置 VNA 测量参数: "S11" / "S21"（部分固件支持 S12/S22）

        trace 为迹线编号 1~4，可同时显示多条 S 参数迹线。
        """
        self._require_vna("set_vna_parameter")
        param = param.upper()
        if param not in self.VNA_PARAMETERS:
            raise ConfigurationError(f"不支持的 S 参数: {param}")
        self.write(f":CALCulate1:PARameter{trace}:DEFine {param}")
        time.sleep(0.05)
        self.write("*WAI")
        self.logger.info(f"[{self.model}] 迹线{trace} 测量参数设为 {param}")

    def get_vna_parameter(self, trace: int = 1) -> str:
        self._require_vna("get_vna_parameter")
        return self.query(f":CALCulate1:PARameter{trace}:DEFine?").strip()

    def get_vna_format(self, trace: int = 1) -> str:
        """查询当前 VNA 迹线显示格式，返回小写键名如 mlog/phase/scomplex"""
        self._require_vna("get_vna_format")
        self.select_trace(trace)
        fmt = self.query(":CALCulate1:FORMat?").strip().upper()
        for key, val in self.VNA_FORMATS.items():
            if val.upper() == fmt:
                return key
        return fmt.lower()

    def set_vna_format(self, fmt: str, trace: int = 1):
        """设置 VNA 迹线显示格式: mlog/phase/gdelay/smith/swr/..."""
        self._require_vna("set_vna_format")
        key = fmt.lower()
        if key not in self.VNA_FORMATS:
            raise ConfigurationError(f"不支持的格式: {fmt}，可选 {list(self.VNA_FORMATS)}")
        self.select_trace(trace)
        time.sleep(0.05)
        self.write(f":CALCulate1:FORMat {self.VNA_FORMATS[key]}")
        time.sleep(0.05)
        self.write("*WAI")
        self.logger.debug(f"[{self.model}] 迹线{trace} 显示格式设为 {self.VNA_FORMATS[key]}")

    def set_trace_count(self, count: int):
        """设置 VNA 迹线数量 1~4"""
        self._require_vna("set_trace_count")
        self.write(f":CALCulate1:PARameter:COUNt {int(count)}")

    def select_trace(self, trace: int):
        """选中指定迹线为当前迹线（后续 marker/格式命令作用于该迹线）"""
        self._require_vna("select_trace")
        self.write(f":CALCulate1:PARameter{int(trace)}:SELect")
        time.sleep(0.05)
        self.write("*WAI")

    def _read_trace_data(self, cmd: str, timeout: float = 30.0) -> list:
        """读取迹线/格式化数据，兼容 ASCII 与 IEEE 488.2 二进制块。

        部分 Siglent 固件对 ``:TRACe:DATA?`` / ``:CALCulate1:DATA?`` 返回二进制块
        （以 ``#`` 开头），若直接用 ``query`` 按 ASCII 读取会触发 protocol error。
        本方法先尝试按 ASCII 读取；若检测到二进制头或 ASCII 解析失败，则回退到
        二进制读取（默认 4 字节小端 float，若失败再试 8 字节）。
        读取成功后主动清空 VISA 缓冲区，避免残留数据影响下一次扫描。
        """
        self.write("*WAI")
        time.sleep(0.05)
        try:
            resp = self.query(cmd, timeout=timeout)
            values = []
            if resp.startswith("#"):
                values = self._parse_binary_block(resp.encode("latin-1"))
            else:
                values = [float(v) for v in resp.split(",") if v.strip()]
            if values:
                # 清空接口，防止长数据回复后下一次 *OPC? 报 VI_ERROR_ABORT
                if self.inst is not None:
                    try:
                        self.inst.clear()
                    except Exception:
                        pass
                return values
        except Exception:
            pass
        # ASCII 读取失败或没有数据，尝试二进制读取
        values = self._read_trace_binary(cmd, timeout=timeout)
        if values and self.inst is not None:
            try:
                self.inst.clear()
            except Exception:
                pass
        return values

    def _read_trace_binary(self, cmd: str, timeout: float = 30.0) -> list:
        """通过 query_binary_values 读取二进制块并转为 float 列表。"""
        if not self.connected or self.inst is None:
            raise ConnectionError(f"[{self.model}] 未连接")
        old_timeout = self.inst.timeout
        self.inst.timeout = int(timeout * 1000)
        try:
            # 先用 4 字节小端 REAL32 尝试
            for dtype, is_big in (("f", False), ("f", True), ("d", False), ("d", True)):
                try:
                    self.write("*WAI")
                    values = self.inst.query_binary_values(
                        cmd, datatype=dtype, is_big_endian=is_big,
                        header_fmt="ieee", container=list)
                    if values:
                        return values
                except Exception:
                    continue
            raise ConnectionError(f"[{self.model}] 无法解析二进制迹线数据")
        finally:
            self.inst.timeout = old_timeout

    @staticmethod
    def _parse_binary_block(raw: bytes) -> list:
        """解析 IEEE 488.2 二进制块为 float 列表（优先 4 字节小端）。"""
        if not raw or raw[0:1] != b"#":
            raise ValueError("不是二进制块")
        # 格式: #<digit_count><length_digits><data>
        digit_count = raw[1] - 48
        length = int(raw[2:2 + digit_count])
        payload = raw[2 + digit_count:2 + digit_count + length]
        for fmt in ("<f", ">f", "<d", ">d"):
            if len(payload) % struct.calcsize(fmt) != 0:
                continue
            try:
                n = len(payload) // struct.calcsize(fmt)
                return list(struct.unpack(fmt * n, payload))
            except Exception:
                continue
        raise ValueError("无法解析二进制块内的浮点数据")

    # ------------------------------------------------------------------
    # Marker
    # ------------------------------------------------------------------
    def set_marker(self, marker: int, on: bool = True):
        """开启/关闭指定 Marker（1~8，VNA 模式 1~7）"""
        self.write(f":CALCulate:MARKer{marker}:STATe {'ON' if on else 'OFF'}")

    def set_marker_mode(self, marker: int, mode: str):
        """设置 Marker 模式

        mode: "normal"（普通）/ "delta"（差值）/ "fixed"（仅 SA）/ "off"
        """
        key = mode.lower()
        modes = self.MARKER_MODES_VNA if self._mode == "vna" else self.MARKER_MODES_SA
        if key not in modes:
            raise ConfigurationError(f"不支持的 Marker 模式: {mode}，可选 {list(modes)}")
        self.write(f":CALCulate:MARKer{marker}:MODE {modes[key]}")
        self.logger.debug(f"[{self.model}] Marker{marker} 模式设为 {modes[key]}")

    def get_marker_mode(self, marker: int) -> str:
        return self.query(f":CALCulate:MARKer{marker}:MODE?").strip()

    def set_marker_position(self, marker: int, x: Frequency):
        """设置 Marker 位置（X 轴，频率）

        需先开启 Marker（set_marker）。频率单位同 set_frequency。
        """
        self.write(f":CALCulate:MARKer{marker}:X {_fmt_freq(x)}")

    def get_marker(self, marker: int) -> dict:
        """读取 Marker 当前 X（Hz）与 Y（dBm/dB）值"""
        x = float(self.query(f":CALCulate:MARKer{marker}:X?"))
        y_resp = self.query(f":CALCulate:MARKer{marker}:Y?").strip()
        # VNA 模式下 Y 可能返回 "amp,0" 或 "amp,phase" 等多值，取第一个作为显示值
        y = float(y_resp.split(",")[0])
        return {"x": x, "y": y}

    def set_marker_peak(self, marker: int):
        """将 Marker 移动到当前迹线峰值"""
        self.write(f":CALCulate:MARKer{marker}:MAXimum")

    def set_marker_peak_track(self, marker: int, on: bool = True):
        """Marker 峰值跟踪开关"""
        self.write(f":CALCulate:MARKer{marker}:CPEak:STATe {'ON' if on else 'OFF'}")

    def set_marker_to_ref_level(self, marker: int):
        """将指定 Marker 处的幅度设为参考电平（Marker→Ref Level）"""
        self.write(f":CALCulate:MARKer{marker}:RLEVel")

    # ------------------------------------------------------------------
    # 参考点（Reference）设置
    # ------------------------------------------------------------------
    def set_marker_reference(self, marker: int, ref_marker: int):
        """设置指定 Delta Marker 的参考 Marker（SA 模式）

        即 "Relative To"：marker 以 ref_marker 为参考点显示差值。
        """
        self.write(f":CALCulate:MARKer{marker}:RELative:TO:MARKer {ref_marker}")
        self.logger.debug(f"[{self.model}] Marker{marker} 参考设为 Marker{ref_marker}")

    def set_reference_marker(self, on: bool = True):
        """开启/关闭参考 Marker R（VNA 模式）

        开启后其余活动 Marker 变为 Delta 模式，以 R 为参考点。
        """
        self._require_vna("set_reference_marker")
        self.write(f":CALCulate:MARKer:REFerence:STATe {'ON' if on else 'OFF'}")

    def marker_all_off(self):
        """关闭所有 Marker"""
        self.write(":CALCulate:MARKer:AOFF")

    # ------------------------------------------------------------------
    # 扫描控制与数据读取
    # ------------------------------------------------------------------
    def single_sweep(self, timeout: float = 30.0):
        """执行一次单次扫描并等待完成（VNA 模式）"""
        self._require_vna("single_sweep")
        # 先清空仪器/接口状态，避免上一次数据读取残留导致下一次 *OPC? 报 abort
        try:
            self.abort_sweep()
        except Exception:
            pass
        self.write("*CLS")
        time.sleep(0.05)
        # 写清除 VISA 缓冲区（针对 USB-TMC 残留数据/EOI 问题）
        if self.inst is not None:
            try:
                self.inst.clear()
            except Exception:
                pass
        self.write("*WAI")
        time.sleep(0.05)
        self.write(":INITiate1:CONTinuous OFF")
        time.sleep(0.05)
        self.write(":INITiate1:IMMediate")
        time.sleep(0.05)
        # 用 write + read 分开等待 *OPC?，避免 pyvisa query 合并命令带来的时序问题
        self.write("*OPC?")
        time.sleep(0.05)
        self.read(timeout=timeout)
        # 确保所有命令/数据已同步
        self.write("*WAI")
        time.sleep(0.1)

    def set_continuous_sweep(self, on: bool = True):
        """连续扫描开关"""
        self.write(f":INITiate1:CONTinuous {'ON' if on else 'OFF'}")

    def abort_sweep(self):
        """中止当前扫描"""
        self.write("ABORt")

    def get_trace(self, trace: int = 1) -> list:
        """读取迹线数据

        SA:  返回各点幅度 (dBm) 列表；
        VNA: 根据当前显示格式返回标量值列表，或复数 [(re, im), ...] 列表。
        """
        self.select_trace(trace)
        values = self._read_trace_data(f":TRACe:DATA? {trace}", timeout=30.0)
        if self._mode == "vna":
            fmt = self.get_vna_format(trace)
            if fmt in self.VNA_COMPLEX_FORMATS:
                return [(values[i], values[i + 1])
                        for i in range(0, len(values) - 1, 2)]
            return values
        return values

    def get_trace_fdata(self, trace: int = 1) -> list:
        """读取 VNA 格式化迹线数据 (:CALCulate:DATA? FDATA)

        部分固件会按 [freq0, amp0, freq1, amp1, ...] 或 [amp0, x0, amp1, x1, ...]
        返回 2*NOP 个数值。本方法返回原始浮点列表，由上层根据频率范围解析。
        """
        self._require_vna("get_trace_fdata")
        self.select_trace(trace)
        return self._read_trace_data(":CALCulate1:DATA? FDATA", timeout=30.0)

    # ------------------------------------------------------------------
    def _require_vna(self, func: str):
        if self._mode != "vna":
            raise ConfigurationError(
                f"{func} 仅在 VNA 模式可用，当前模式: {self._mode}，"
                f"请先 set_mode('vna')")

    def _pre_disconnect(self):
        # 恢复连续扫描，避免仪器停留在单次扫描状态
        try:
            if self._mode == "vna":
                self.set_continuous_sweep(True)
        except Exception:
            pass
