@echo off
REM LabEng 一键打包脚本。先安装依赖：pip install pyinstaller
cd /d %~dp0
pip install pyinstaller --quiet
pyinstaller --onefile --windowed --name LabEng --clean lab_engine_app.py
if errorlevel 1 (
    echo 打包失败，请把上方错误信息反馈给维护者。
    pause
    exit /b 1
)
REM 例程目录放到 exe 旁边：运行时扫描这里，方便直接增删例程文件
xcopy /e /i /y lab_engine\routines dist\routines
echo.
echo 完成：dist\LabEng.exe
echo 使用方式：把 dist 整个文件夹发给使用者，双击 LabEng.exe。
echo 数据、参数、日志会生成在 exe 旁边的 data\ 目录。
pause
