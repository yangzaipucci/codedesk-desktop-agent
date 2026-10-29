# Windows 打包说明

要求 Windows x64、Python 3.12、Microsoft Edge WebView2 Runtime、Inno Setup 6。正式发布还需要 Windows SDK SignTool 和受信任的代码签名证书。完整操作见 [签名发布流程](signing.md)。

1. 创建专用虚拟环境，安装 `.[build,test]`。固定的完整依赖见根目录 `requirements-lock.txt`，也可先按该文件安装。
2. 配置证书指纹，执行 `.venv\Scripts\python scripts\build_windows.py --check-signing`。没有证书时此命令应失败。
3. 提交最终源码，执行 `.venv\Scripts\python scripts\build_windows.py --iscc "编译器所在目录\ISCC.exe"`。
4. 完整目录位于 `build/signed/application/CodeDesk`，安装包、便携压缩包和签名清单位于 `release/signed/1.0.1/`。必须携带完整目录，不能只拷贝入口 exe。
5. 按签名文档执行安装验收，再使用 `scripts/publish_github.ps1` 发布。未通过验收不能正式发布。

脚本先构建目录形式的独立 `WorkspaceMCP.exe`，再构建无控制台主程序，把 MCP 目录、ui 和 sample_workspace 一并收集。签名阶段逐一验证所有 EXE/DLL/PYD 等原生文件，再通过 Inno `SignTool` 和 `SignedUninstaller` 签名安装器、安装临时副本及卸载器。签名结果包含 SHA256、发布者和时间戳；已有可信第三方签名保留。

源码模式资源根目录为项目目录，打包模式为 `sys._MEIPASS`。设置和运行记录保存在 `%LOCALAPPDATA%\CodeDesk`。安装包安装到当前用户的Programs目录，无需管理员权限，提供开始菜单、可选桌面快捷方式和标准卸载入口。

没有证书仅能显式使用 `--unsigned`，输出隔离到 `build/unsigned` 和 `release/unsigned/1.0.1`，文件名带 `-unsigned`。正式发布脚本不接受这些开发包。旧 `dist/` 和根 release 下的 1.0.0 文件是历史预览，不会被新流程覆盖。

不应将 `.venv`、build、dist、release、证书私钥或真实模型 Key 推入 Git。安装包附在 Release 中。自动安装验收后仍需人工验证原生窗口、配置输入、真实模型对话、工具修改和中断。当前无证书，尚未产出可信签名版本。
