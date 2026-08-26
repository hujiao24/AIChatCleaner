# AI 对话清理工具

清除 Cursor、VS Code Copilot、Codex 在 **Windows 本地** 与 **WSL** 中的聊天对话记录。

## 使用可执行文件

直接双击运行：

```
dist/AIChatCleaner.exe
```

界面操作：
1. 勾选要清理的目标（Windows / WSL 分组）
2. 选择 WSL 发行版（如有）
3. 点击 **扫描** 查看占用
4. 可选 **模拟运行**，确认后点击 **清除**

## 从源码构建 exe

**方式一：双击 `build.bat`**（推荐，Windows 下最简单）

**方式二：在终端里运行**

```powershell
cd D:\develop\cleaner
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

> 说明：`.ps1` 在 Windows 上默认会用记事本打开，这是正常现象；需要用 PowerShell 显式执行，不要直接双击 `.ps1`。

**方式三：手动命令**

```powershell
cd D:\develop\cleaner
pip install -r requirements.txt
pyinstaller --noconfirm --clean AIChatCleaner.spec
```

产物位于 `dist\AIChatCleaner.exe`。

## 支持的目标

| 环境 | 应用 | 清理范围 |
|------|------|----------|
| Windows | Cursor | `agent-transcripts`、对话搜索索引 |
| Windows | Copilot Chat | `session-store.db`、空窗口会话 |
| Windows | Codex | `~\.codex\sessions\` |
| WSL | Cursor | `~/.cursor/projects/*/agent-transcripts/` |
| WSL | Copilot Chat | `~/.vscode-server/.../session-store.db` |
| WSL | Codex | `~/.codex/sessions/` |

## 注意

- 清理前请关闭 Cursor / VS Code
- 删除不可恢复，建议先模拟运行
- 不会删除登录配置（如 Codex 的 `auth.json`）
