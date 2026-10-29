# 构建与运行 1.1.0

源码启动和三步使用见 ../README.md。Windows x64，Python 3.12（开发），Node.js 24，Edge WebView2；分发包自带官方 Python 3.13.17 运行环境。

## 前端与检查

执行 `npm ci`、`npm run build`、`npm test`。不要手改 ui/app.js；修改 frontend/ 后重新构建。执行 `python -m unittest discover -s tests -v`。requirements-lock.txt 和 package-lock.json 固定依赖。

## 分发包

执行 `python scripts/build_portable.py --installer --iscc "Inno Setup目录\ISCC.exe"`。输出位于 release/portable/1.1.0/：便携 ZIP、带 unsigned 标记的预览 Setup.exe 与 SHA256SUMS.txt。build/portable/1.1.0/CodeDesk/ 是完整可运行目录，双击 Start-CodeDesk.cmd。必须保留 app/ 和 runtime/。

运行环境从 python.org 下载并核对官方 SHA256；应用依赖用锁定版本安装，前端离线打包。portable-manifest.json 记录版本、源码提交及逐文件 SHA256。包内不包含用户设置、真实 Key、虚拟环境或本地会话。

GitHub Actions 的 package 作业在一次性 Windows 运行器构建、安装、核对文件、启动后端、读取 UI/示例、调用独立 MCP、卸载，输出 functional-installation.json。此功能检查与受信任代码签名验收分开，不混淆二者。

## 受信任签名发布

证书存储区与 SignTool 配置后，执行 scripts/build_windows.py 默认签名构建，再执行 verify_installation.py 和正式发布门禁。详细指令见 signing.md。无证书时不能产生可信发布者签名，也不应修改系统保护设置来制造通过结果。
