@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo 正在构建 AIChatCleaner.exe ...
echo.

pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo 依赖安装失败，请检查 Python / pip 是否可用。
    pause
    exit /b 1
)

pyinstaller --noconfirm --clean AIChatCleaner.spec
if errorlevel 1 (
    echo.
    echo 构建失败。
    pause
    exit /b 1
)

echo.
echo 完成: dist\AIChatCleaner.exe
echo.
pause
