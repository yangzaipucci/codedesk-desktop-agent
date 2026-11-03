# CodeDesk 修改日志

按北京时间记录已核验的三个工作日期：2026-10-27、2026-10-29、2026-11-03。10 月 27 日为需求及本地过程记录，另外两天有对应 Git 提交。

完整模块说明见 [开发记录](docs/development-log.md)，逐条提交见 [提交索引](docs/development/commit-index.md)。

## 2026-11-03 · 1.2.0 补丁、兼容性与教程

- 技能：代码审查、Python 测试、联网研究三个技能；先注入目录，再通过 read 按需加载正文。
- 定制：全局与项目 AGENTS.md、执行前拦截、修改后测试、结束时只读 reviewer；保留四个内置工具。
- 持久化任务：逐步保存、内核任务锁、强制中断恢复、文件内容幂等校验和通知去重。
- MCP：本机 HTTP 服务默认 `http://127.0.0.1:8001/mcp`，要求独立令牌和 Origin 校验；保留 stdio。
- Windows 修复：中文验收 JSON 兼容英文控制台；检查点共享锁限次重试；失败保留具体诊断和部分报告。
- 验证：应用基线 `b2952d1` 的 Windows 工作流通过 118 项 Python、5 项前端测试，以及安装、启动、补丁、MCP 和卸载检查。
- 教程：约 7 分 07 秒的中文配音与字幕视频、飞书 MCP 配置和操作步骤。飞书为配置教学，未执行真实账号授权。
- 文档：补齐三天开发记录、原始提交索引、README 入口和教程资料。

功能与修复提交：[982dba6](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/982dba6)、[439b479](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/439b479)、[1872557](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/1872557)、[b2952d1](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/b2952d1)。

## 2026-10-29 · 基础桌面版与 1.1.0 工作台

- 基础工具：实现 read、write、edit、bash，以及修改快照、哈希冲突检查、差异和撤销。
- 智能体：流式模型接口、工具循环、预算、超时、真正取消、上下文管理和失败恢复。
- 模型：桌面配置 DeepSeek 及常见兼容接口；Key 默认保留内存，可选系统凭据管理器，记录脱敏。
- 工作台：原生窗口、默认浅色与深色切换、多标签代码编辑、项目文件树和搜索、Markdown 语法支持与回答渲染、可拖动分栏与终端。
- 模式：Agent、Plan、Debug、Multitask、Ask；队列保持独立上下文并顺序执行。
- 联网：外部 MCP 发现和实际调用；日期、天气、网页、文献元数据和计算；应用内真实 DeepSeek 问答与代码修复联调。
- 分发：官方 Python 独立运行环境、便携包、Windows 安装器、CI 安装检查、哈希清单和代码签名发布流程。
- 材料：README、设计报告、截图、失败恢复记录、演示视频及完整提交包；发布 1.1.0 预览附件。

基础提交从 [951301c](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/951301c) 开始；主要工作台提交为 [0c142a0](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/0c142a0)，真实 API 和交付修正见 [ae3f4b8](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/ae3f4b8)、[74da197](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/74da197)、[a9966f6](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/a9966f6)。

## 2026-10-27 · 需求整理与本地初始工作

- 阅读课程 PPT 第 35–40 页，整理桌面程序、四个内置工具、外部 MCP、现场演示及提交材料要求。
- 明确完整前后端、公开仓库、版本发布、安装包、README、设计报告和运行记录等交付项。
- 确认 Key 在桌面交互输入，优先 DeepSeek，同时保留常见兼容模型接口。
- 开展本地初始项目工作并保留项目目录；按用户要求暂停，后续开发与集中提交发生在 10 月 29 日。

当日依据为需求沟通与本地工作记录，未发现当日 Git 提交。此条作为开发过程记录保存。
