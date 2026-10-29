# Windows 打包说明

要求Windows x64、Python3.12、Microsoft Edge WebView2 Runtime，以及Inno Setup6（仅构建安装包时需要）。

1. 创建专用虚拟环境，安装 `.[build,test]`。固定的完整依赖见根目录 `requirements-lock.txt`，也可先按该文件安装。
2. 在项目根目录执行 `.venv\Scripts\python scripts\build_windows.py --iscc "编译器所在目录\ISCC.exe"`。
3. `dist/CodeDesk/CodeDesk.exe` 是便携目录版入口，必须连同整个目录使用。`release/CodeDesk-Setup-1.0.0.exe` 是用于GitHub Release的安装包，不能只上传一个缺资源的入口exe。

脚本先构建独立 `WorkspaceMCP.exe`，再构建无控制台主程序，把MCP、ui和sample_workspace作为资源一并收集，最后调用 `scripts/installer.iss`。

源码模式资源根目录为项目目录，打包模式为 `sys._MEIPASS`。设置和运行记录保存在 `%LOCALAPPDATA%\CodeDesk`。安装包安装到当前用户的Programs目录，无需管理员权限，提供开始菜单、可选桌面快捷方式和标准卸载入口。

不应将`.venv`、build、dist、release或真实Key推入Git历史。安装包附在Release中。构建后要在未配置Key的环境打开，验证窗口、配置输入、文件读取、真实模型对话、MCP调用和中断。当前构建未签名，需要由提交者确认新电脑上的实际安装体验。
