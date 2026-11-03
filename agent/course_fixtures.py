"""Explicit controlled model fixtures: actual tools; never model-quality claims."""
import json


def call(name, arguments, identity):
    return {'role': 'assistant', 'content': None, 'tool_calls': [{'id': identity, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments, ensure_ascii=False)}}]}


class RepairProvider:
    """Deliberately propose a bad empty-input fix, then act on real hook feedback."""
    def __init__(self):
        self.turn = 0
        self.red_seen = False

    async def complete(self, messages, definitions, emit):
        self.turn += 1
        usage = {'total_tokens': 0}
        if self.turn == 1:
            return call('read', {'path': 'stats.py'}, 'inspect-source'), usage
        if self.turn == 2:
            return call('edit', {'path': 'stats.py', 'old': '    return sum(nums) / len(nums)', 'new': '    if not nums:\n        return 1\n    return sum(nums) / len(nums)'}, 'deliberate-error'), usage
        result = json.loads(messages[-1]['content'])
        test = result.get('autotest', {})
        if self.turn == 3 and test.get('status') == 'failed' and test.get('summary'):
            self.red_seen = True
            return call('edit', {'path': 'stats.py', 'old': '        return 1', 'new': '        return 0'}, 'repair-from-feedback'), usage
        if not self.red_seen or test.get('status') != 'passed':
            raise ValueError('真实测试反馈未完成红转绿，不能宣布修复。')
        return {'role': 'assistant', 'content': '已修复 mean 的空输入问题，相关测试已实际通过。'}, usage


class DiffProvider:
    """A fixed controlled policy compares actual command batching, not LLM quality."""
    def __init__(self):
        self.turn = 0

    async def complete(self, messages, definitions, emit):
        self.turn += 1
        has_skill = 'review-diff:' in messages[0]['content']
        if has_skill:
            if self.turn == 1:
                return call('read', {'path': 'skill://review-diff/SKILL.md'}, 'load-workflow'), {}
            if self.turn == 2:
                return call('read', {'path': 'skill://review-diff/scripts/collect_diff.py'}, 'load-helper'), {}
            if self.turn == 3:
                import os,shlex,sys
                path = json.loads(messages[-1]['content'])['package_file']
                quote = (lambda s: "'" + str(s).replace("'", "''") + "'") if os.name == 'nt' else shlex.quote
                command = ('& ' if os.name == 'nt' else '') + quote(sys.executable) + ' ' + quote(path) + ' --workspace .'
                return call('bash', {'command': command, 'timeout': 20}, 'collect-diff'), {}
        else:
            sequence = [('read', {'path': 'AGENTS.md'}), ('read', {'path': 'README.md'}), ('bash', {'command': 'git diff --stat'}), ('bash', {'command': 'git diff --no-ext-diff --no-textconv --unified=3'})]
            if self.turn <= len(sequence):
                name,args = sequence[self.turn-1]
                return call(name,args,'baseline-'+str(self.turn)), {}
        return {'role': 'assistant', 'content': '已获取实际 Git 差异及统计。此受控试验比较工具调用次数，不代表真实模型效果提升。'}, {}
