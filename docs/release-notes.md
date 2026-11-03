# CodeDesk 1.2.0：技能、定制、常驻与 MCP 端口

在 1.1.0 桌面工作台上补齐三项课程补丁，保持四个内置模型工具与既有界面。

- 技能：三种实际工作流，先注入目录，通过 read 按需读取正文；附六条触发验收与披露比例报告。
- 定制：30 行项目 AGENTS.md、全局/项目两层注入，动作前拦截、修改后测试、结束时只读 reviewer。每项可关闭，定制上下文增量有明确上限。
- 常驻：逐步原子落盘、硬中断续跑、内核任务锁、定时轮询及完成通知，提供带 SHA256 完成条件的幂等步骤。
- MCP：本机 Streamable HTTP 服务默认 http://127.0.0.1:8001/mcp，使用独立 MCP 令牌，校验认证与 Origin；原有 stdio 不使用端口。
- python app.py inspect --output reports 实际执行验收，输出 skill/custom/daemon/mcp 四份 JSON；README 提供开关、命令、配置与限制。

API Key 继续在桌面设置中填写。预览安装器明确带 unsigned 标记，正式受信任签名流程保持独立门禁。具体验证以对应 Windows CI、功能安装收据和 reports 为准。

仓库：https://github.com/yangzaipucci/codedesk-desktop-agent

## 开发记录与教程资料补充

补充 [2026-10-27、10-29、11-03 三天开发记录](development-log.md)、[原始提交索引](development/commit-index.md)和 [中文操作教程](tutorial/README.md)。10 月 27 日为需求与本地过程记录，另外两天有 Git 提交。教程含字幕、章节及飞书只读配置示例，真实飞书账号尚未授权。

此次为文档及教学材料归档，应用与安装包仍对应已验收的 1.2.0 构建 b2952d1，保留原发布附件和安装收据。
