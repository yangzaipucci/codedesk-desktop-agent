# CodeDesk 三天开发记录

日期按北京时间记录。已核验的工作日期是 **2026-10-27、2026-10-29、2026-11-03**。10 月 27 日依据需求沟通和本地初始工作；10 月 29 日、11 月 3 日另有 Git 提交可核对。

[提交索引](development/commit-index.md)覆盖应用构建基线 `b2952d1a378238f9afa4d06929a446a0575b4fe2` 及之前的 27 次提交：10 月 29 日 23 次，11 月 3 日 4 次。本次补充日志的文档提交另见 [仓库提交页](https://github.com/yangzaipucci/codedesk-desktop-agent/commits/main)。

## 2026-10-27 需求与方案确认

### 课程要求

阅读 PPT 第 35–40 页，将任务拆成桌面窗口、文件/代码/对话分区、四个内置工具、模型与工具循环、真正取消、后端独立运行、外部 MCP 实际调用、安装分发和现场演示。列出 README、report.md、运行轨迹、打包说明、演示视频和依赖锁定等材料。

### 模型与本地初始工作

确认 Key 在桌面输入，优先使用 DeepSeek，并保留常见兼容接口。开展本地初始工作，保留 desktop-agent 项目目录；收到暂停要求后停止继续操作。当日属于需求和本地过程记录，没有对应 Git 提交，功能实现与验证以之后的记录为准。

## 2026-10-29 基础版、工作台与首次完整分发

### 文件工具和智能体循环

实现 read 的行号与分页、write 的父目录创建和原子替换、edit 的唯一精确匹配、bash 的输出/退出码/超时/截断。加入文件字节快照、哈希冲突检测、差异和撤销；模型循环支持预算、上下文管理、重复调用限制、取消及失败恢复。

主要文件：`agent/tools.py`、`agent/runtime.py`。提交：[d2b1b58](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/d2b1b58)、[ecf8bfe](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/ecf8bfe)。

### 模型、凭据和服务接口

接入兼容 Chat Completions/function tools 的流式模型接口，校验结束与参数完整性。桌面提供服务、地址、模型、Key 和连接测试，可选系统凭据保存，并对记录脱敏。本地 FastAPI 服务使用会话令牌，提供 REST、SSE 和 WebSocket。

主要文件：`agent/provider.py`、`agent/settings.py`、`server/app.py`。提交：[67fd616](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/67fd616)、[d204aec](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/d204aec)、[96d378b](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/96d378b)。

### 界面、编辑器与五种模式

增加默认浅色和可切换深色主题、多文件编辑、语法高亮、查找、项目搜索、新建文件/目录、保存冲突检查、文件引用、Markdown 语法支持与回答渲染、差异及撤销。文件栏和对话栏可左右调整，终端可上下调整；代码和详细命令集中在中间区域。

增加 Agent、Plan、Debug、Multitask、Ask。队列任务保持独立上下文并顺序执行，只读模式在工具执行路由再次检查权限。

主要文件：`frontend/`、`agent/workspace.py`、`agent/modes.py`、`agent/tasks.py`。提交：[0c142a0](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/0c142a0)、[74da197](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/74da197)。

### MCP、联网与真实模型调试

连接 stdio 与 Streamable HTTP MCP，保留服务和工具来源。独立演示进程返回实际工作目录信息；联网服务提供系统时间、天气、网页、文献元数据和计算。增加文本型 PDF/DOCX 和图片读取。

使用桌面配置的真实 DeepSeek API 验证日期、南京天气、代码解释和 Crossref 文献元数据，保留 arXiv 失败后的处理过程。代码修复联调先复现两个失败测试，再读取并精确修改代码，复测两个用例通过。

证据：[1.1.0 验证记录](validation.md)、[真实 API 调试轨迹](real-api-debug-trace.md)。提交：[972c2ff](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/972c2ff)、[0c142a0](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/0c142a0)、[ae3f4b8](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/ae3f4b8)。

### 安装、签名流程与提交材料

打包官方 Windows Python 独立运行环境、前端、示例和锁定依赖，提供便携包与 Inno Setup 安装器。Windows CI 检查安装、文件一致性、启动、UI、MCP 和卸载，通过检查的附件用于预览发布。另设受信任签名和时间戳门禁，当前预览保留 unsigned 标记。

补充 README、设计报告、截图、运行轨迹、演示与提交文件夹；发布 1.1.0 附件。该阶段记录为 98 项 Python、5 项前端检查通过。

提交：[6488af8](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/6488af8)、[0500e9f](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/0500e9f)、[a9966f6](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/a9966f6)。

## 2026-11-03 三个补丁、兼容性修复与教程

### A 技能系统

增加 code-review、python-tests、web-research 三个技能，将元数据目录与正文分离。目录先注入，正文按任务通过已有 read 工具加载，支持来源层级、触发规则和路径边界。验收为三项技能、六条触发用例、零误触发，披露比例 16.734。

主要文件：`agent/skills.py`、`agent_assets/skills/`。证据：[技能报告](../reports/skill_report.json)。计量采用 UTF-8 字节上界，不是厂商精确 tokenizer。

### B 定制层与三类 hook

新增 30 行项目 AGENTS.md、全局模板和两层注入。执行前拦截危险动作，Python 修改后检查语法并运行相关测试，结束时使用独立只读 reviewer。禁止 reviewer 执行 write/bash，并限制凭据读取和主上下文增量。

验收实际触发两种拦截并给出替代方案，执行相关测试并检查只读约束；主上下文计量为 416。验收 reviewer 使用明确标注的受控 Provider，生产仍调用桌面配置的模型 API。

主要文件：`agent/capabilities.py`、`agent/hooks.py`、`agent/reviewer.py`、`agent/runtime.py`。证据：[定制报告](../reports/custom_report.json)。

### C 持久化任务

新增 daemon create/run/watch/list，步骤执行前后原子保存状态，内核锁防止同一任务并发执行，写入按内容哈希判断重入与冲突，通知按任务去重。验收在前三步后强制结束独立进程，从第4步恢复，确认已完成文件没有重写且只通知一次。

主要文件：`agent/daemon.py`、`examples/daemon-plan.json`。证据：[断点恢复报告](../reports/daemon_report.json)。该能力需显式启动，不自动安装开机服务；任意外部副作用不保证 exactly-once。

### MCP 服务与设置界面

新增 app.py mcp，HTTP 默认 `http://127.0.0.1:8001/mcp`，仅监听本机，使用独立令牌与 Origin 校验；stdio 不占 TCP 端口。桌面增加补丁开关、保存恢复、测试状态和完成通知。验收实际完成 SDK 工具发现与调用，并检查未认证 401、非法来源 403。

主要文件：`agent/mcp_service.py`、`agent/mcp_client.py`、`frontend/patches.js`、`server/app.py`。证据：[MCP 报告](../reports/mcp_report.json)。测试选择临时空闲端口，产品默认仍为 8001。

### Windows 修复与安装验证

修复英文控制台输出中文验收 JSON 的编码错误；保留失败测试诊断和部分报告；修复检查点文件被短暂共享锁占用时直接失败的问题，加入限次重试，持续权限错误仍明确返回。

应用基线 b2952d1 的 [Windows 工作流](https://github.com/yangzaipucci/codedesk-desktop-agent/actions/runs/41643645469)通过 118 项 Python、5 项前端测试，以及安装、启动、资源、补丁报告、MCP 和卸载检查。[1.2.0 发布页](https://github.com/yangzaipucci/codedesk-desktop-agent/releases/tag/v1.2.0)保留对应包、哈希和功能安装收据。

提交：[982dba6](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/982dba6)、[439b479](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/439b479)、[1872557](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/1872557)、[b2952d1](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/b2952d1)。

### 教学视频与文档归档

制作 1920×1080、约 7 分 07 秒的中文配音教程，提供 40 条字幕和 20 个章节。覆盖补丁入口、实际验收、MCP 配置、端口区别、飞书官方 stdio 和权限排查。视频采用实际 UI 关键画面与报告，明确标记非连续录屏；制作时实际完成本地 MCP 发现与调用。

飞书部分为无真实密钥的配置教学，尚未授权真实账号。当前版本的自定义飞书工具应使用 Agent 模式。材料见 [教程入口](tutorial/README.md)和 [飞书配置步骤](tutorial/操作步骤与官方资料.md)。

本次归档补齐修改日志、原始提交索引与 README 链接。应用和安装包继续使用已通过验收的 1.2.0 基线，日志及教程作为文档更新单独提交。

## 核对入口

- [逐条提交索引](development/commit-index.md)：日期、原始提交说明、改动文件及提交链接。
- [机器可读提交记录](development/commits.json)：应用基线之前的作者时间、提交时间和文件路径。
- [修改摘要](../CHANGELOG.md)、[补丁验收说明](patches-validation.md)及 [四份报告](../reports/)。


### 2026-11-03：完整增量要求对齐

在收到两份完整课件和增量作业说明后，按逐项审查补齐技能可移植目录、指定验收入口、真实BPE计量、规则向上查找、强制推送拦截、三行失败摘要、两次自动修复、独立差异审查、定时技能和系统通知。开关对比与测试全部实际运行，受控模型验证和真实API能力分别标明。新增阶段标签保留历史发布，不改写日期、不补造七天提交。更新报告与编号2连续操作录像，重新构建并验证安装包后生成新的最终确定档。

实际提交：[技能阶段](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/64a3001)、[定制阶段](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/fcfea31)。其余当前提交见仓库提交页；历史提交索引保持其明确标注的快照范围。
