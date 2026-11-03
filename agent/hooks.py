"""Three deterministic hook events: pre-tool policy, post-edit tests, stop review."""
import ast
from pathlib import Path
import re
import shlex
import sys
import tempfile
import uuid

from agent.capabilities import enabled


class PolicyDenied(ValueError):
    pass


class Hooks:
    def __init__(self, workspace, directory):
        self.workspace, self.directory = Path(workspace).resolve(), directory
        self.autotest_history = []

    def before(self, name, arguments):
        if not enabled('hooks', self.directory):
            return
        path = str(arguments.get('path', '')).replace('\\', '/').lower()
        credential = any(p == '.env' or p.startswith('.env.') and p != '.env.example' or p.endswith(('.pem', '.pfx', '.p12', '.key')) for p in path.split('/'))
        if name in {'write', 'edit'} and credential:
            raise PolicyDenied('已拦截凭据文件修改。替代方案：写入 .env.example 占位配置；真实模型 Key 在桌面设置填写。')
        if name != 'bash':
            return
        command = str(arguments.get('command', ''))
        canonical = command.replace('`', '').lower()
        if re.search(r'\bgit\b[^;\n]*\bpush\b[^;\n]*(?:--force(?:-with-lease)?\b|(?:^|\s)-[a-z]*f[a-z]*(?:\s|$)|(?:^|\s)\+)', canonical):
            raise PolicyDenied('已拦截 Git 强制推送。替代方案：先 git diff 与 git status 核对，再普通 git push；撤销已提交更改用 git revert。')
        if re.search(r'\bgit\b[^;\n]*\breset\s+--hard\b', canonical):
            raise PolicyDenied('已拦截 Git 强制重置。替代方案：先 git diff 检查；需要撤销提交用 git revert，需要恢复文件先预览再 git restore。')
        if re.search(r'\brm\s+[^;\n]*-(?:[a-z]*r[a-z]*|-[a-z]*recursive)\b',canonical):
            raise PolicyDenied('已拦截递归删除命令。替代方案：先列出目标文件并逐项确认，使用范围明确的非递归操作。')
        dangerous = (r'\brm\s+[^;\n]*-[a-z]*r[a-z]*f', r'\brm\s+[^;\n]*-[a-z]*f[a-z]*r', r'\brm\s+[^;\n]*--recursive', r'\bremove-item\b[^;\n]*-r(?:ecurse)?\b', r'\b(?:rd|rmdir|del|erase)\b[^;\n]*/s\b', r'\bgit\s+(?:reset\s+--hard|clean\s+-[a-z]*f)', r'\b(?:format-volume|diskpart|format\.com|iex|invoke-expression)\b', r'-(?:encodedcommand|enc)\b')
        if any(re.search(pattern, canonical) for pattern in dangerous):
            raise PolicyDenied('已拦截破坏性或隐藏执行命令。替代方案：先列出目标文件、查看 diff，再使用非递归且范围明确的操作；不要使用强制递归删除。')
        if re.search(r'(?<![\w.])\.env(?!\.example)(?:\b|[\s\'"/\\])', canonical) and re.search(r'write|set-content|add-content|out-file|>|tee|copy|move', canonical):
            raise PolicyDenied('已拦截通过命令写入 .env。替代方案：使用 .env.example 占位文件，模型 Key 在桌面配置。')

    async def after_edit(self, path, tools):
        if not enabled('hooks', self.directory) or not enabled('autotest', self.directory):
            return {'status': 'skipped', 'reason': 'disabled'}
        target = tools.resolve(path)
        if target.suffix.lower() == '.py':
            try:
                ast.parse(target.read_text(encoding='utf-8-sig'), filename=target.name)
            except (SyntaxError, UnicodeError) as error:
                return self.record({'status': 'failed', 'syntax_ok': False, 'summary': f'用例：{target.name} 语法检查\n期望：有效 Python 语法\n实际：{str(error).splitlines()[0][:180]}', 'exit_code': 1})
        test_name = target.name if target.name.startswith('test_') else 'test_' + target.name
        test = target.parent / test_name
        if not test.is_file():
            test_dir = self.workspace / 'tests'
            if not test_dir.is_dir() or not any(test_dir.glob('test_*.py')):
                return {'status': 'skipped', 'syntax_ok': True, 'reason': 'No related test file; verification incomplete'}
            test = test_dir
            test_name = 'test_*.py'
        executable = Path(sys.executable)
        if executable.name.lower() == 'pythonw.exe':
            executable = executable.with_name('python.exe')
        start = (test if test.is_dir() else test.parent).relative_to(self.workspace).as_posix()
        # JSON string quoting is not used as shell escaping. Windows uses the
        # single-quoted PowerShell literal form; POSIX uses shlex.quote.
        import os
        quote = (lambda s: "'" + str(s).replace("'", "''") + "'") if os.name == 'nt' else shlex.quote
        # A fresh cache prefix also avoids READING stale same-second .pyc files.
        cache = str(Path(tempfile.gettempdir()) / ('codedesk-tests-' + uuid.uuid4().hex))
        command = ('& ' if os.name == 'nt' else '') + quote(str(executable)) + ' -B -X ' + quote('pycache_prefix=' + cache) + ' -m unittest discover -s ' + quote(start) + ' -p ' + quote(test_name) + ' -q'
        if os.name == 'nt':
            command += '; exit $LASTEXITCODE'
        result = await tools.bash(command, timeout=20)
        text = result.get('stderr','') + '\n' + result.get('stdout','')
        failure = re.search(r'^(?:FAIL|ERROR): (.+)$', text, re.M)
        assertion = re.search(r'^AssertionError: (.+)$', text, re.M)
        actual, expected = '全部测试通过', '所有断言通过'
        if not result['ok']:
            actual = assertion[1] if assertion else ('超时' if result.get('timed_out') else '命令或测试失败，退出码 ' + str(result.get('exit_code')))
            unequal = re.match(r'(.+?) != (.+?)(?:\s*:|$)', actual)
            if unequal: actual,expected = unequal[1],unequal[2]
        summary = '用例：' + (failure[1] if failure else test_name)[:160] + '\n期望：' + expected[:160] + '\n实际：' + actual[:160]
        ran = re.search(r'Ran (\d+) tests?', text)
        return self.record({'status': 'passed' if result['ok'] else 'failed', 'syntax_ok': True, 'test': test_name, 'exit_code': result.get('exit_code'), 'timed_out': result.get('timed_out',False), 'tests_run': int(ran[1]) if ran else 0, 'summary': summary})

    def record(self, result):
        result['injected_lines'] = len(result['summary'].splitlines())
        self.autotest_history.append(dict(result))
        return result
