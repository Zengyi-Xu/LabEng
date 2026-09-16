# Cornerstone 260 USB 通信桥（32 位）
# Cornerstone.dll / CyUSB.dll 是 Newport 官方 .NET 2.0 程序集，内部在
# 64 位进程下会因 IntPtr.ToInt32 溢出而无法枚举设备，因此必须在 32 位
# Windows PowerShell 进程中加载。本脚本从标准输入读取 JSON 命令行，
# 执行后向标准输出写回单行 JSON 结果。
#
# 协议：每行一个 JSON 对象 { "id": <序号>, "cmd": "<命令名>", "args": [...] }
# 响应：{ "id": <序号>, "ok": true, "result": <值> }
#    或 { "id": <序号>, "ok": false, "error": "<消息>" }
# 响应带回请求 id，主进程据此丢弃超时调用的迟到响应，避免错位。
param(
    [string]$DllPath = "C:\Program Files (x86)\Newport\Mono Utility 5.0.4\Cornerstone DLL\Cornerstone.dll"
)

$ErrorActionPreference = 'Stop'
[Threading.Thread]::CurrentThread.CurrentCulture = [Globalization.CultureInfo]::InvariantCulture

Add-Type -Path $DllPath
$script:mono = New-Object CornerstoneDll.Cornerstone($false)

function Send-Result($obj) {
    [Console]::Out.WriteLine(($obj | ConvertTo-Json -Compress -Depth 5))
}

while ($true) {
    $line = [Console]::In.ReadLine()
    if ($null -eq $line) { break }
    if ([string]::IsNullOrWhiteSpace($line)) { continue }

    try {
        $req = $line | ConvertFrom-Json
        $id = $req.id
        $cmd = [string]$req.cmd
        $a = $req.args
        if ($null -eq $a) { $a = @() }
        $result = $null

        switch ($cmd) {
            'find_devices'       { $result = $script:mono.findDevices() }
            'connect'            { $result = $script:mono.connect() }
            'disconnect'         { $script:mono.disconnect(); $result = $true }
            'get_last_message'   { $result = $script:mono.getLastMessage() }
            'get_device_name'    { $result = $script:mono.getDeviceName() }
            'get_wavelength'     { $result = $script:mono.getWavelength() }
            'set_wavelength'     { $result = $script:mono.setWavelength([double]$a[0]) }
            'get_shutter'        { $result = $script:mono.getShutter() }
            'set_shutter'        { $result = $script:mono.setShutter([bool]$a[0]) }
            'get_grating'        { $result = $script:mono.getGrating() }
            'set_grating'        { $result = $script:mono.setGrating([int]$a[0]) }
            'get_grating_label'  { $result = $script:mono.getGratingLabel([int]$a[0]) }
            'get_grating_lines'  { $result = $script:mono.getGratingLines([int]$a[0]) }
            'get_grating_offset' { $result = $script:mono.getGratingOffset([int]$a[0]) }
            'get_filter'         { $result = $script:mono.getFilter() }
            'set_filter'         { $result = $script:mono.setFilter([int]$a[0]) }
            'get_filter_label'   { $result = $script:mono.getFilterLabel([int]$a[0]) }
            'get_units'          { $result = $script:mono.getUnits() }
            'set_units'          { $result = $script:mono.setUnits([CornerstoneDll.WAVELENGTH_UNITS]$a[0]) }
            'get_slit_width'     { $result = $script:mono.getSlitWidth([CornerstoneDll.CS_PORT]$a[0]) }
            'set_slit_width'     { $result = $script:mono.setSlitWidth([CornerstoneDll.CS_PORT]$a[0], [int]$a[1]) }
            'get_bandpass'       { $result = $script:mono.getBandpass() }
            'set_bandpass'       { $result = $script:mono.setBandpass([double]$a[0]) }
            'query_double'       { $result = $script:mono.getDoubleResponseFromCommand([string]$a[0]) }
            'query_int'          { $result = $script:mono.getIntResponseFromCommand([string]$a[0]) }
            'query_string'       { $result = $script:mono.getStringResponseFromCommand([string]$a[0]) }
            'send_command'       { $result = $script:mono.sendCommand([string]$a[0]) }
            'get_response'       { $result = $script:mono.getResponse() }
            'handshake'          { $script:mono.handshake([bool]$a[0]); $result = $true }
            'set_step'           { $script:mono.setStep([int]$a[0]); $result = $true }
            'set_wait_time'      { $script:mono.setWaitTime([int]$a[0]); $result = $true }
            'get_wait_time'      { $result = $script:mono.getWaitTime() }
            'set_device_timeout' { $script:mono.setDeviceTimeout([uint32]$a[0]); $result = $true }
            default { throw "unknown command: $cmd" }
        }

        Send-Result @{ id = $id; ok = $true; result = $result }
    }
    catch {
        Send-Result @{ id = $id; ok = $false; error = $_.Exception.Message }
    }
}
