# Windows 签名与发布流程

## 当前状态

本项目提供证书预检查、完整原生二进制签名、Inno 临时组件/卸载器签名、安装验收和正式发布门禁。当前分发为预览，CodeDesk 安装器未附受信任发布者签名；具备证书与 Windows SDK SignTool 后，可执行下列正式签名流程。

签名证书与大模型 API Key 是两种不同凭据。模型 Key 继续只在桌面设置内输入，可选择保存在 Windows 凭据管理器；本流程不要求用户把模型 Key 写进代码或构建配置。

## 为什么要签整个安装链

本机 CodeIntegrity 日志显示，被阻止的是 Inno Setup 解压出的 `CodeDesk-Setup-1.0.0.tmp`，策略为 `VerifiedAndReputableDesktop`。只给最终 Setup.exe 补签，不能解决内部临时副本未签的问题。

Inno 的 `SignTool=codedesk` 配合 `SignedUninstaller=yes`，会在编译过程中调用指定签名程序，签安装器、临时副本和卸载器。主应用、MCP 和其 DLL/PYD 则在编译安装包之前完成签名。MCP 采用目录打包，使依赖 DLL 能逐一检查。

官方依据：[SignedUninstaller](https://jrsoftware.org/ishelp/topic_setup_signeduninstaller.htm)、[Inno SignTool](https://jrsoftware.org/ishelp/topic_setup_signtool.htm)、[Microsoft SignTool](https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool)、[智能应用控制的代码签名要求](https://learn.microsoft.com/en-us/windows/apps/develop/smart-app-control/code-signing-for-smart-app-control)。

## 准备证书和工具

1. 通过受信任的代码签名提供方获得证书，并按提供方要求配置硬件令牌/HSM 等私钥访问方式。当前实现使用 Windows `CurrentUser\My` 或 `LocalMachine\My` 证书存储。云签名服务需要另接服务适配器，当前脚本没有声称支持任意云签名服务。
2. 安装 [Windows SDK](https://developer.microsoft.com/en-us/windows/downloads/windows-sdk/)，包含 Windows 签名工具。SignTool 默认从 PATH 或 SDK x64 目录发现。
3. 使用同一 Windows 账户执行构建。需要令牌 PIN 时在证书提供方的可信界面输入，不发到聊天、不放入脚本。脚本不导出私钥、不接受 PFX 密码参数。证书文件后缀已加入 `.gitignore`，提交时仍需检查待提交文件。

以下在项目根目录的 PowerShell 执行。替换为证书管理界面显示的真实 SHA1 指纹；它是公开标识，不是私钥：

```powershell
$env:CODEDESK_SIGN_CERT_SHA1 = '替换为40位十六进制证书指纹'
# 仅证书位于本机计算机账户时设置；用户账户默认不需要：
# $env:CODEDESK_SIGN_STORE = 'machine'
# 若无法自动找到工具，可指定其完整路径：
# $env:CODEDESK_SIGNTOOL = 'C:\Program Files (x86)\Windows Kits\10\bin\版本\x64\signtool.exe'
# 时间戳端点默认如下；可改为证书提供方推荐的 RFC3161 服务：
$env:CODEDESK_TIMESTAMP_URL = 'http://timestamp.digicert.com'
.venv\Scripts\python.exe scripts\build_windows.py --check-signing
```

预检查要求：证书有私钥、用途为代码签名、在有效期内、证书链和在线吊销检查通过，且不是自签名证书。无网络导致吊销检查失败也会停止；不会自动放宽信任。SHA1 仅用于定位证书，实际文件摘要和时间戳摘要使用 SHA256。

## 正式构建与验收

先提交最终源码及文档，保持工作区干净，再执行：

```powershell
.venv\Scripts\python.exe scripts\build_windows.py --iscc '.build-temp\inno\ISCC.exe'
```

工具检查任一步失败均返回非零退出码。已有可信第三方签名保留并验证；未签名原生文件用指定证书签名；异常签名直接拒绝。项目签名必须有可信时间戳，SignTool 的警告返回码也视为失败。输出为：

- `build/signed/application/CodeDesk/`：完整签名目录。
- `release/signed/1.1.0/CodeDesk-Setup-1.1.0.exe`：安装器。
- 同目录 `CodeDesk-Portable-1.1.0-win64.zip`、`signing-manifest.json` 和 `SHA256SUMS.txt`。

在没有安装过 CodeDesk 的 Windows 测试账户/虚拟机执行自动验收。验收使用项目内唯一临时目录，保留系统保护；已有安装记录时直接拒绝，避免覆盖用户安装：

```powershell
.venv\Scripts\python.exe scripts\verify_installation.py `
  --directory build\signed\application\CodeDesk `
  --installer release\signed\1.1.0\CodeDesk-Setup-1.1.0.exe `
  --report release\signed\1.1.0\signing-manifest.json
```

验收先复核签名和哈希，再静默安装，核对安装后的文件、卸载器签名/时间戳，启动已安装的独立后端，读取界面资源和示例项目，调用真实 MCP 子进程，最后卸载。仅全部通过才生成 `installation-acceptance.json` 的 `passed` 结果。失败保留本地 `.build-temp/acceptance-*/` 日志；不会生成虚假成功记录。若安装中途失败或卸载器签名异常，可能留有测试安装，应在该测试环境检查后清理，禁止执行未验证的卸载程序。

自动验收不替代人工检查原生窗口、设置表单及真实模型对话。在目标 Windows 保持原有保护策略，双击安装器和应用，检查发布者、窗口、桌面配置 Key、工具修改和中断；最后由测试人员核对卸载。真实模型 Key 不放入验收记录或截图。

## 发布到 GitHub

需要已登录的 GitHub CLI。源码版本、当前提交、构建和验收必须对应。不要在验收后修改源码；需要修改时重新提交、构建和验收。

```powershell
.\scripts\publish_github.ps1 -Repository 'yangzaipucci/codedesk-desktop-agent'
```

发布脚本在任何 GitHub 写入之前执行以下检查：签名清单及文件哈希、完整原生文件清单、安装验收及对应安装包哈希、便携包内全部资源与目录一致、干净的工作区、构建来源提交。通过后刷新校验文件，再推送当前提交与版本标签，上传安装包、便携包、签名清单、验收记录和校验文件。

脚本只创建尚不存在的版本，不覆盖 Release 或移动旧标签；已有 origin 必须与参数仓库一致。失败后按报错修复，保留已产生的可核对记录，再重试。

## 无证书时的开发构建

```powershell
.venv\Scripts\python.exe scripts\build_windows.py --unsigned --iscc '.build-temp\inno\ISCC.exe'
```

开发包写到 `release/unsigned/1.1.0/`，文件名含 `-unsigned`，清单模式为 `unsigned`。这些包会被安装验收和正式发布脚本拒绝；本机无需反复尝试执行已知会被智能应用控制阻止的安装器。

签名不能保证所有 Windows 策略或杀毒产品放行。本流程不关闭智能应用控制/Defender，不添加系统信任根，不使用自签名证书冒充公开受信任的发布者，也不把尚未完成的签名构建描述为已通过安装验收。


## 1.1.0 运行环境分发

另提供 scripts/build_portable.py 生成的官方 Python 运行环境源码应用包。运行环境保留原厂签名，CodeDesk 应用仍不冒充已获得可信发布者签名。GitHub CI 的 functional-installation.json 仅记录预览安装功能检查，不替代本文的签名安装验收或 release_check.py 门禁。
