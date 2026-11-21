@echo off
set "HF_ENDPOINT=https://hf-mirror.com"
set "HF_HUB_OFFLINE=1"
chcp 65001 >nul
cd /d %~dp0

if not exist .venv\Scripts\activate.bat (
    echo [错误] 还没有环境, 请先运行 setup.bat
    pause & exit /b 1
)

call .venv\Scripts\activate.bat

echo.
echo 正在获取本机局域网 IP(手机访问用)...
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    for /f "tokens=* delims= " %%b in ("%%a") do set LAN_IP=%%b
)

echo.
echo   电脑访问:  http://localhost:8000
echo   手机访问:  http://%LAN_IP%:8000
echo   关闭服务:  直接关掉本窗口
echo.
echo ============================================
echo  [!] 引擎后台加载, 服务通常 3-5 秒即可访问.
echo  浏览器将自动打开; 没弹就手动访问上面的地址.
echo ============================================

start "as-autoopen" /min python "%~dp0as_autoopen.py" 8000
python run.py
pause
