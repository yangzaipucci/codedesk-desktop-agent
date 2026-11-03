# 1.3.1 验证与复现

运行 README 的三条 python -m app.inspect 指定命令，退出码0才通过。JSON 中 test_tier 与 token_measure 说明证据层级，任何一步失败不会伪报通过。

- reports/skill_report.json：六技能、九条触发、零误触发、BPE渐进披露、同代码关闭/开启对比、真实脚本与MCP。
- reports/custom_report.json：上级规则、拒绝原因、真实Runtime两次红转绿、三行摘要、只读审查与上下文计量。
- reports/daemon_report.json：实际硬终止进程、第4步恢复、三次到点技能、重复轮询去重、实际系统通知请求。
- reports/mcp_report.json：HTTP服务认证401、来源403、发现工具与实际调用。
- reports/baseline_report.json：禁用增量后实际检查四工具、图片与界面资源。
- reports/course_report.json：独立校验器检查指定字段及阈值。运行 python scripts/verify_course_reports.py reports 可复核。
- reports/measurement_report.json：同一份技能的字节/BPE计量差异，用于报告的真实判断纠正。

后端测试 python -m unittest discover -s tests -q，前端 npm test，构建 npm run build。安装包从对应成功的 Windows CI 产物发布，随包 functional-installation.json 绑定安装器哈希，验证安装、资源、启动、MCP、补丁报告与卸载。portable-manifest.json 绑定实际源提交。

这些自动验收使用稳定受控模型，不需要提供真实API Key，也不冒充真实模型质量评价。生产对话和审查调用桌面配置的服务。飞书真实账号未授权，配置教程不等同于账号已连通。

Windows CI 的完整回归为125项后端、5项前端通过，计数见 reports/regression_report.json；安装以对应功能收据为准。系统通知字段表示Windows接口已接受，实际可见性由系统设置决定。
