# CodeDesk 1.2.0：技能、定制、常驻与 MCP 端口

在 1.1.0 桌面工作台上补齐三项课程补丁，保持四个内置模型工具与既有界面。

- 技能：三种实际工作流，先注入目录，通过 read 按需读取正文；附六条触发验收与披露比例报告。
- 定制：30 行项目 AGENTS.md、全局/项目两层注入，动作前拦截、修改后测试、结束时只读 reviewer。每项可关闭，定制上下文增量有明确上限。
- 常驻：逐步原子落盘、硬中断续跑、内核任务锁、定时轮询及完成通知，提供带 SHA256 完成条件的幂等步骤。
- MCP：本机 Streamable HTTP 服务默认 http://127.0.0.1:8001/mcp，使用独立 MCP 令牌，校验认证与 Origin；原有 stdio 不使用端口。
- python app.py inspect --output reports 实际执行验收，输出 skill/custom/daemon/mcp 四份 JSON；README 提供开关、命令、配置与限制。

API Key 继续在桌面设置中填写。预览安装器明确带 unsigned 标记，正式受信任签名流程保持独立门禁。具体验证以对应 Windows CI、功能安装收据和 reports 为准。

仓库：https://github.com/yangzaipucci/codedesk-desktop-agent
