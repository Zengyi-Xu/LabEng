"""Cornerstone 260 单色仪 - USB 接口（Newport 官方 DLL 桥接）

CS260 的 USB 版不是虚拟串口，官方通信方式是 Newport 提供的
Cornerstone.dll（.NET 2.0，依赖 CyUSB.dll + Cypress USB 驱动）。
该 DLL 在 64 位进程下枚举设备时会触发 IntPtr 溢出，只能在 32 位进程
中运行，因此本驱动通过 32 位 Windows PowerShell 子进程桥接
（见 _cornerstone_bridge.ps1），主进程通过 JSON 行协议与其通信。

使用 USB 接口前，必须先在 Windows 上安装 Newport Mono Utility（例如
5.0.4 版本），否则找不到 Cornerstone.dll 和 Cypress USB 驱动。
"""
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from .monochromator import Monochromator
from ..core.exceptions import ConnectionError, CommandError, TimeoutError

DEFAULT_DLL_CANDIDATES = [
    r"C:\Program Files (x86)\Newport\Mono Utility 5.0.4\Cornerstone DLL\Cornerstone.dll",
    r"C:\Users\Xuzen\Documents\MonoUT5.0.4\Cornerstone DLL\Cornerstone.dll",
]

# 32 位 Windows PowerShell（系统自带，.NET Framework 4.x 可加载 .NET 2.0 程序集）
PS_X86 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                      "SysWOW64", "WindowsPowerShell", "v1.0", "powershell.exe")

# 首次启动时 Add-Type 编译 DLL 较慢，给首次请求更长的超时
_BRIDGE_STARTUP_TIMEOUT = 60.0


class _CornerstoneBridge:
    """管理 32 位 PowerShell 桥子进程，JSON 行协议通信"""

    def __init__(self, dll_path: str):
        self.dll_path = dll_path
        script = Path(__file__).with_name("_cornerstone_bridge.ps1")
        if not script.exists():
            raise ConnectionError(f"找不到桥接脚本: {script}")

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        self._proc = subprocess.Popen(
            [PS_X86, "-NoProfile", "-STA", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-File", str(script),
             "-DllPath", dll_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            startupinfo=startupinfo,
        )
        self._responses: "queue.Queue[str]" = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self._first_request = True
        self._next_id = 0
        self._dead = False

    def _read_loop(self):
        for line in self._proc.stdout:
            self._responses.put(line.strip())

    def request(self, cmd: str, args: Optional[list] = None,
                timeout: Optional[float] = None) -> object:
        if self._dead:
            raise ConnectionError("Cornerstone 桥已失效，请重新连接")
        if self._proc.poll() is not None:
            self._dead = True
            raise ConnectionError("Cornerstone 桥进程已退出")
        if timeout is None:
            timeout = _BRIDGE_STARTUP_TIMEOUT if self._first_request else 30.0
        self._first_request = False

        self._next_id += 1
        req_id = self._next_id
        payload = json.dumps({"id": req_id, "cmd": cmd, "args": args or []})
        try:
            self._proc.stdin.write(payload + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            self._dead = True
            raise ConnectionError(f"Cornerstone 桥进程通信失败: {e}")

        # 按请求 id 匹配响应；超时调用（DLL 卡死）的迟到响应直接丢弃
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._dead = True
                self.close()
                raise TimeoutError(f"Cornerstone 桥超时 ({timeout}s): {cmd}，桥已销毁")
            try:
                line = self._responses.get(timeout=remaining)
            except queue.Empty:
                continue
            try:
                resp = json.loads(line)
            except json.JSONDecodeError:
                raise CommandError(f"桥返回无效响应: {line[:200]}")
            if resp.get("id") != req_id:
                continue
            if not resp.get("ok"):
                raise CommandError(f"{cmd} 失败: {resp.get('error', '未知错误')}")
            return resp.get("result")

    def close(self):
        try:
            if self._proc.poll() is None:
                self._proc.terminate()
                self._proc.wait(timeout=5)
        except Exception:
            try:
                self._proc.kill()
            except Exception:
                pass


class Cornerstone260(Monochromator):
    """Cornerstone 260 单色仪（USB 接口，经 Newport DLL 桥接）

    用法::

        mono = Cornerstone260()
        mono.connect()
        print(mono.idn())
        mono.goto_wavelength(500.0)
        mono.disconnect()
    """

    def __init__(self, dll_path: Optional[str] = None, timeout: float = 60.0,
                 logger=None):
        super().__init__(port="USB", baudrate=0, timeout=timeout, logger=logger)
        self.dll_path = dll_path or self._find_dll()
        self._bridge: Optional[_CornerstoneBridge] = None

    @staticmethod
    def _find_dll() -> str:
        for candidate in DEFAULT_DLL_CANDIDATES:
            if os.path.exists(candidate):
                return candidate
        raise ConnectionError(
            "未找到 Cornerstone.dll。请确认已安装 Newport Mono Utility "
            "（例如 5.0.4 版本），或显式传入 dll_path 指向 Cornerstone.dll"
        )

    # --- 连接管理 ---

    def connect(self, retries: int = 3) -> bool:
        for attempt in range(1, retries + 1):
            try:
                self.logger.info(f"[{self.model}] 尝试连接 USB (第{attempt}次)")
                self._bridge = _CornerstoneBridge(self.dll_path)
                found = self._bridge.request("find_devices")
                if not found:
                    raise ConnectionError("未找到 Cornerstone 设备，检查 USB 连接/驱动")
                if not self._bridge.request("connect"):
                    raise ConnectionError(self.get_last_message() or "connect() 返回 False")
                self.connected = True
                self.logger.info(f"[{self.model}] 连接成功: {self.get_last_message()}")
                return True
            except Exception as e:
                self.logger.warning(f"[{self.model}] 连接失败: {e}")
                self._close_bridge()
                time.sleep(1)
        raise ConnectionError(f"[{self.model}] USB 连接失败，已重试{retries}次")

    def disconnect(self):
        if self._bridge is not None:
            try:
                self._bridge.request("disconnect", timeout=10)
            except Exception as e:
                self.logger.warning(f"[{self.model}] 断开时出错: {e}")
            finally:
                self._close_bridge()
                self.connected = False
                self.logger.info(f"[{self.model}] 已断开")

    def _pre_disconnect(self):
        # 单色仪快门不等同源表输出：断开时不自动关闭快门，
        # 避免影响光路中的其他光路配置
        pass

    def _close_bridge(self):
        if self._bridge is not None:
            self._bridge.close()
            self._bridge = None

    def __del__(self):
        self._close_bridge()

    # --- 底层通信（BaseInstrument 接口兼容） ---

    def write(self, cmd: str):
        self._require_bridge().request("send_command", [cmd])

    def read(self, timeout: Optional[float] = None) -> str:
        return str(self._require_bridge().request("get_response", timeout=timeout))

    def query(self, cmd: str, timeout: Optional[float] = None) -> str:
        return str(self._require_bridge().request(
            "query_string", [cmd], timeout=timeout))

    def _require_bridge(self) -> _CornerstoneBridge:
        if not self._bridge:
            raise ConnectionError(f"[{self.model}] 未连接")
        return self._bridge

    def _req(self, cmd: str, args: Optional[list] = None) -> object:
        return self._require_bridge().request(cmd, args)

    # --- 设备信息 ---

    def _clean(self, raw: str) -> str:
        """DLL 返回的字符串缓冲区可能含 \x00 与残留行，取首个有效行"""
        return " ".join(str(raw).replace("\x00", " ").split())

    def idn(self) -> str:
        """查询仪器标识（DLL 响应缓冲区可能含残留字符，做清洗）"""
        cleaned = self._clean(self._req("query_string", ["*IDN?"]))
        idx = cleaned.find("Cornerstone")
        if idx >= 0:
            return cleaned[idx:]
        return cleaned

    def get_last_message(self) -> str:
        return self._clean(self._req("get_last_message"))

    # --- 波长 ---

    def get_wavelength(self) -> float:
        return float(self._req("get_wavelength"))

    def set_wavelength(self, wavelength_nm: float) -> bool:
        ok = bool(self._req("set_wavelength", [float(wavelength_nm)]))
        self.logger.debug(f"[{self.model}] WAVE {wavelength_nm:.3f} -> {ok}")
        return ok

    def goto_wavelength(self, wavelength_nm: float, wait: bool = True,
                        timeout: Optional[float] = None,
                        tolerance_nm: float = 0.05) -> float:
        """移动到指定波长；wait 时轮询实际位置直到进入容差范围"""
        self.set_wavelength(wavelength_nm)
        if not wait:
            return self.get_wavelength()
        deadline = time.time() + (timeout if timeout is not None else self.timeout)
        while True:
            actual = self.get_wavelength()
            if abs(actual - wavelength_nm) <= tolerance_nm:
                return actual
            if time.time() > deadline:
                raise TimeoutError(
                    f"[{self.model}] 波长移动超时: 目标 {wavelength_nm:.3f} nm, "
                    f"当前 {actual:.3f} nm"
                )
            time.sleep(0.2)

    def measure(self) -> dict:
        """读取当前波长位置"""
        return {
            "wavelength": self.get_wavelength(),
            "timestamp": time.time(),
            "status": self.get_last_message()
        }

    # --- 快门 ---

    def get_shutter(self) -> bool:
        """True = 快门打开"""
        return bool(self._req("get_shutter"))

    def set_shutter(self, state) -> bool:
        """state: True/"O"/"OPEN" 打开；False/"C"/"CLOSE" 关闭"""
        if isinstance(state, str):
            open_ = state.upper() in ("O", "OPEN")
        else:
            open_ = bool(state)
        self._req("set_shutter", [open_])
        return open_

    # --- 光栅 / 滤光片 ---

    def get_grating(self) -> str:
        """返回 "编号,线数,偏移" 格式的当前光栅信息"""
        return self._clean(self._req("get_grating"))

    def get_grating_number(self) -> int:
        return int(float(self.get_grating().split(",")[0]))

    def set_grating(self, grating: int, wait: bool = True,
                    timeout: Optional[float] = None) -> bool:
        ok = bool(self._req("set_grating", [int(grating)]))
        if ok and wait:
            deadline = time.time() + (timeout if timeout is not None else self.timeout)
            while True:
                current = self.get_grating().split(",")[0].strip()
                if current == str(grating):
                    break
                if time.time() > deadline:
                    raise TimeoutError(f"[{self.model}] 光栅切换超时: {grating}")
                time.sleep(0.3)
        return ok

    def get_grating_info(self, grating: int) -> dict:
        return {
            "label": self._clean(self._req("get_grating_label", [int(grating)])),
            "lines": int(self._req("get_grating_lines", [int(grating)])),
            "offset": float(self._req("get_grating_offset", [int(grating)])),
        }

    def get_filter(self) -> int:
        return int(self._req("get_filter"))

    def set_filter(self, position: int) -> bool:
        return bool(self._req("set_filter", [int(position)]))

    # --- 其他 ---

    def get_units(self) -> str:
        return self._clean(self._req("get_units"))

    def set_units(self, unit: str):
        """unit: NM / UM / WN"""
        self._req("set_units", [unit.upper()])

    def get_slit_width(self, port: str = "INPORTA") -> int:
        return int(self._req("get_slit_width", [port.upper()]))

    def set_slit_width(self, port: str, width: int):
        self._req("set_slit_width", [port.upper(), int(width)])

    def get_bandpass(self) -> float:
        return float(self._req("get_bandpass"))

    def get_device_name(self) -> str:
        return self._clean(self._req("get_device_name"))
