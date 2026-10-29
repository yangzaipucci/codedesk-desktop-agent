# CodeDesk 桌面智能体

Python 原生桌面代码助手与问答智能体。默认浅色，可切换深色；API Key 在桌面设置中输入。支持 DeepSeek 及 OpenAI 兼容接口，模型回复由用户配置的服务生成。

公开仓库：https://github.com/yangzaipucci/codedesk-desktop-agent

## 三步使用

1. 从 [Release](https://github.com/yangzaipucci/codedesk-desktop-agent/releases) 下载 1.1.0 安装包并安装；也可完整解压便携 ZIP，双击 `Start-CodeDesk.cmd`。
2. 在右上角“模型与连接”选择服务、模型，输入自己的 API Key，测试后保存。可选保存到 Windows 凭据管理器。
3. 打开项目文件夹，选择助手模式并发送需求。中间编辑代码，右侧查看结果，底部显示实际命令输出。

运行环境为 Windows x64 与 Microsoft Edge WebView2 Runtime。分发包自带 Python，不要求老师另装 Python。未配置 Key 时仍可手动编辑、搜索文件和运行终端；模型对话需有效 Key 与网络。

![浅色桌面工作台](docs/screenshots/01-main.png)

## 可以完成什么

- 多标签代码编辑、语法高亮、查找、折叠、撤销、保存全部、新建文件/目录、项目全文搜索与快速打开。
- 关联文件与选中代码（Ctrl L）；Agent 读、写、精确编辑、运行测试；修改差异与用户撤销。保存冲突时拒绝覆盖。
- Agent 执行任务；Plan 只读制定计划，可一键转 Agent；Debug 复现、修复和复测；Ask 只读问答；Multitask 使用独立上下文依次执行多个任务。
- 实际系统时间、实时天气、通用网页检索、公开网页阅读、Crossref/arXiv 文献检索、可校验的数学计算。来源由 MCP 工具返回，重要事实需核对原网页。读取文本型 PDF、DOCX 及图片。
- 代码片段、命令和详细工具数据集中在中间区域；右侧保留结果与简短进度。文件栏、对话栏、终端高度均可拖动，双击分界线恢复。
- 浅深主题、桌面模型配置、模型列表、连接测试、MCP 服务配置、任务中断与运行记录导出。同一工作区最近会话可重启恢复。

四个内置模型工具严格为 **read / write / edit / bash**。联网、计算、时间工具通过独立 MCP 进程接入并标注来源。工具参数、真实输出、diff 与失败记录都可以查看。

## 源码启动（3 步）

1. Windows 安装 Python 3.12 和 Node.js 24，克隆仓库后执行 `python -m venv .venv`。
2. 执行 `.venv\Scripts\python -m pip install -r requirements-lock.txt`，再执行 `npm ci` 与 `npm run build`。
3. 执行 `.venv\Scripts\python app.py`，在桌面中填写 Key。

前端源码在 `frontend/`，离线构建产物在 `ui/`；前端不依赖外部 CDN。完整 Python 和 npm 版本锁定文件均入仓库。

## 验证与构建

`python -m unittest discover -s tests -v`、`npm test`、`npm run build`。GitHub Actions 在 Windows 执行回归、构建分发包并在独立运行器验证安装/启动/MCP/卸载。

便携与预览安装包：`python scripts/build_portable.py --installer --iscc "Inno Setup目录\ISCC.exe"`。官方 Python 运行环境校验原始下载哈希，分发包保留文件清单与源码提交。完整签名构建、时间戳及发布门禁见 [签名流程](docs/signing.md)，当前预览安装包文件名明确带 `unsigned`。

独立后端：`python app.py --headless --port 8765`。后端仅监听 127.0.0.1；使用控制台本机会话 token 认证（不是模型 Key）。`POST /api/run` 的 JSON 为 `{"prompt":"任务","mode":"agent"}`，curl.exe 加 `-N` 查看 SSE；`POST /api/stop` 中断，`GET /api/trace` 导出记录。

## 数据和边界

Key 默认仅留在内存；选择系统保存后由 Windows 凭据管理器保存，配置 JSON、源码、浏览器持久存储和安装包均不保存真实 Key。设置/会话/撤销快照位于 `%LOCALAPPDATA%\CodeDesk`，对外分享记录前检查项目内容。

文件工具限制所选目录；bash 使用当前用户权限，工作目录不是操作系统沙箱。命令对 Git、网络、依赖和文件的副作用需要人工审阅。撤销只覆盖登记的文件修改。关闭“联网查询”是模型行为约束，不是操作系统断网机制。

本项目提供课程级桌面工作台，尚不包含 Cursor 的扩展市场、完整语言服务器、Tab 预测补全、远程协作与并行工作树。Multitask 为串行队列。扫描 PDF 需 OCR，联网源可能限流或不可达，文献元数据不等于已读全文或已核实同行评审。其他服务商有预设，但本次真实 Key 实测使用 DeepSeek。

材料：[设计报告](report.md)、[构建说明](docs/build.md)、[验证记录](docs/validation.md)、[现场演示与抽查](docs/demo-guide.md)、[运行记录](docs/trace.md)、[视频](demo.mp4)。
