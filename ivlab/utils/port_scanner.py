"""串口扫描工具"""
import serial
import serial.tools.list_ports
from typing import List, Dict


def list_com_ports() -> List[Dict]:
    """列出所有可用COM端口"""
    ports = []
    for p in serial.tools.list_ports.comports():
        ports.append({
            "port": p.device,
            "description": p.description,
            "hwid": p.hwid,
            "vid": p.vid,
            "pid": p.pid
        })
    return ports


def find_instrument_ports(keywords: List[str] = None) -> List[Dict]:
    """根据关键词查找可能的仪器端口"""
    if keywords is None:
        keywords = ["USB Serial", "FTDI", "Prolific", "CH340", "Keithley", "Newport"]

    all_ports = list_com_ports()
    matches = []
    for p in all_ports:
        desc = p["description"].upper()
        if any(kw.upper() in desc for kw in keywords):
            matches.append(p)
    return matches


def test_port(port: str, baudrate: int = 9600, timeout: float = 1.0) -> bool:
    """测试端口是否可打开"""
    try:
        ser = serial.Serial(port, baudrate, timeout=timeout)
        ser.close()
        return True
    except Exception:
        return False


def interactive_select_port() -> str:
    """交互式选择COM端口"""
    print("\n可用串口列表:")
    ports = list_com_ports()
    if not ports:
        print("未找到任何串口！")
        return input("手动输入COM端口 (如 COM3): ").strip()

    for i, p in enumerate(ports, 1):
        print(f"  [{i}] {p['port']} - {p['description']}")

    choice = input("\n选择端口编号 (或输入完整端口名): ").strip()
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(ports):
            return ports[idx]["port"]
    except ValueError:
        pass
    return choice
