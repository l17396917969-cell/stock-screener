@echo off
chcp 65001 >nul
:: ==========================================
:: 将项目完全打包为 Windows 独立执行程序
:: ==========================================

echo [INFO] 正在检查 Python 环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] 未检测到 Python，无法打包！
    pause
    exit /b
)

:: 进入独立的打包环境防止系统各种乱七八糟包冲突
if not exist "build_venv\Scripts\activate.bat" (
    echo [INFO] 正在创建干净的打包虚拟环境...
    python -m venv build_venv
)

call build_venv\Scripts\activate.bat

echo [INFO] 安装依赖包及 PyInstaller...
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple

echo [INFO] 开始打包程序，请耐心等待 (可能需要 3-5 分钟)...
:: 清理旧的构建文件
if exist "build" rmdir /s /q "build"
if exist "dist\量化审计系统" rmdir /s /q "dist\量化审计系统"

pyinstaller --clean screener.spec

if %errorlevel% neq 0 (
    echo [ERROR] 打包失败，请检查控制台输出！
    pause
    exit /b
)

echo [SUCCESS] ==========================================
echo 打包成功！
echo 生成的独立程序文件夹位于当前目录下的: dist\量化审计系统
echo 你可以将 "dist\量化审计系统" 整个文件夹发送给无环境的电脑。
echo 直接双击文件夹里的 [量化审计系统.exe] 即可运行！
echo [SUCCESS] ==========================================

pause
