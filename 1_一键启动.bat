@echo off
chcp 65001 >nul
:: ==========================================
:: 股票量化审计系统 - Windows 一键启动脚本
:: 作用: 自动创建虚拟环境，安装依赖包，并启动服务
:: ==========================================

echo [INFO] 正在检查 Python 环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] 未检测到 Python！
    echo 请前往 https://www.python.org/downloads/ 下载并安装 Python。
    echo 安装时请务必勾选 "Add Python to PATH" 选项！
    pause
    exit /b
)

:: 检查是否存在 venv 文件夹
if not exist "venv\Scripts\activate.bat" (
    echo [INFO] 首次运行，正在创建独立的 Python 虚拟环境...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] 创建虚拟环境失败。
        pause
        exit /b
    )
)

echo [INFO] 正在激活虚拟环境...
call venv\Scripts\activate.bat

echo [INFO] 正在检查并安装依赖库 (这可能需要几分钟)...
:: 使用国内清华镜像加速下载
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo [ERROR] 依赖包安装失败，请检查网络连接。
    pause
    exit /b
)

echo [INFO] 依赖检查完毕，正在启动应用服务器...
echo [INFO] 如果弹出防火墙提示，请允许访问网络。
echo --------------------------------------------------
echo 系统启动后，请在浏览器中打开: http://127.0.0.1:5000
echo --------------------------------------------------

:: 设置环境变量，防止 akshare 的代理报错
set NO_PROXY=localhost,127.0.0.1,.eastmoney.com,.10jqka.com.cn,.sina.com.cn,.baidu.com,.126.net,.szse.cn,.sse.com.cn,.cninfo.com.cn
set no_proxy=%NO_PROXY%

python app.py

pause
