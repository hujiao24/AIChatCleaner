# 构建 AIChatCleaner.exe
Set-Location $PSScriptRoot
pip install -r requirements.txt
pyinstaller --noconfirm --clean AIChatCleaner.spec
Write-Host "`n完成: dist\AIChatCleaner.exe"
