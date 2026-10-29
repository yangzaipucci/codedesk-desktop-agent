MODES = {
    'agent': 'Agent 模式：按用户目标读取、修改代码并运行适当验证；控制修改范围。',
    'plan': 'Plan 模式：只能读取与分析，输出目标、步骤、涉及文件、验证方案和风险。禁止修改文件、执行命令或声称已经实现。给出计划后等待用户切换 Agent 执行。',
    'debug': 'Debug 模式：先收集真实报错和相关代码，尽量复现；提出可检验的原因，做最小修复，再重跑相关用例。不能编造复现、测试或运行结果。',
    'ask': 'Ask 模式：只读地解释代码、回答问题，可查询公开信息；禁止改写文件、执行命令或安装依赖。代码建议以文本给出。',
}
READ_ONLY = {'plan', 'ask'}


def validate_mode(mode):
    if mode not in MODES:
        raise ValueError('请选择 Agent、Plan、Debug 或 Ask；多任务请添加到任务队列。')
    return mode
