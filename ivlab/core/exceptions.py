"""自定义异常类"""

class InstrumentError(Exception):
    """仪器相关错误的基类"""
    pass

class ConnectionError(InstrumentError):
    """连接失败"""
    pass

class CommandError(InstrumentError):
    """指令执行失败"""
    pass

class TimeoutError(InstrumentError):
    """响应超时"""
    pass

class ConfigurationError(InstrumentError):
    """配置错误"""
    pass

class ScanError(InstrumentError):
    """扫描过程中出错"""
    pass
