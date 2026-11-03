# 项目地图
app/：桌面入口与无界面验收命令，app.py 保留安装快捷方式兼容入口。
agent/：模型循环、四工具、技能加载、hooks、审查、常驻任务。
server/：本机 API；frontend/：编辑器界面源码；ui/：构建产物。
skills/：可移植技能；agent_assets/：安装包随附规则和离线分词表。
tests/：行为与安全回归；scripts/：构建、安装和签名发布检查。

# 构建与测试
npm run build
python -m unittest discover -s tests -q
python -m app.selftest
python -m app.inspect skills --out reports/skill_report.json
python -m app.inspect custom --out reports/custom_report.json
python -m app.inspect daemon --out reports/daemon_report.json

# 代码风格
仅保留 read/write/edit/bash 四个内置模型工具，外部能力通过 MCP。
先读再做唯一精确 edit，保留 UTF-8、BOM 与换行风格。
失败要返回真实错误；验证没有执行时不得声称通过。
技能目录只注入 name/description，正文按需读取。
审查上下文独立，只允许 read 和受限制的 git diff。

# 安全与项目坑
禁止修改 .env、私钥和 .git 内部文件；Key 只在桌面配置。
禁止递归强删、强制推送与强制重置；拒绝时说明替代方案。
Windows 命令使用 PowerShell；子进程保留退出码和超时。
Python 编译缓存可能遮盖快速修复，自动测试禁用字节码缓存。
后台每步持久化，恢复前核对目标哈希，避免覆盖外部更改。
稳定前缀保持顺序，审查只回最终摘要；不回注完整 traceback。
保留能力开关、任务停止、界面工具详情和差异预览。
完成修改要更新 README 与实际生成的验收 JSON。
