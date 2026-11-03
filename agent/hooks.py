"""Three deterministic hook events: pre-tool policy, post-edit tests, stop review."""
import ast
from pathlib import Path
import re
import shlex
import sys

from agent.capabilities import enabled


class PolicyDenied(ValueError):
    pass


class Hooks:
    def __init__(self, workspace, directory):
        self.workspace, self.directory = Path(workspace).resolve(), directory

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
        if re.search(r'\brm\s+[^;\n]*-(?:[a-z]*r[a-z]*|-[a-z]*recursive)\b',canonical):
            raise PolicyDenied('已拦截递归删除命令。替代方案：先列出目标文件并逐项确认，使用范围明确的非递归操作。')
        dangerous = (r'\brm\s+[^;\n]*-[a-z]*r[a-z]*f', r'\brm\s+[^;\n]*-[a-z]*f[a-z]*r', r'\brm\s+[^;\n]*--recursive', r'\bremove-item\b[^;\n]*-r(?:ecurse)?\b', r'\b(?:rd|rmdir|del|erase)\b[^;\n]*/s\b', r'\bgit\s+(?:reset\s+--hard|clean\s+-[a-z]*f)', r'\b(?:format-volume|diskpart|format\.com|iex|invoke-expression)\b', r'-(?:encodedcommand|enc)\b')
        if any(re.search(pattern, canonical) for pattern in dangerous):
            raise PolicyDenied('已拦截破坏性或隐藏执行命令。替代方案：先列出目标文件、查看 diff，再使用非递归且范围明确的操作；不要使用强制递归删除。')
        if re.search(r'(?<![\w.])\.env(?!\.example)(?:\b|[\s\'"/\\])', canonical) and re.search(r'write|set-content|add-content|out-file|>|tee|copy|move', canonical):
            raise PolicyDenied('已拦截通过命令写入 .env。替代方案：使用 .env.example 占位文件，模型 Key 在桌面配置。')

    async def after_edit(self, path, tools):
        if not enabled('autotest', self.directory) or Path(path).suffix.lower() != '.py':
            return {'status': 'skipped', 'reason': 'disabled or non-Python file'}
        target = tools.resolve(path)
        try:
            ast.parse(target.read_text(encoding='utf-8-sig'), filename=target.name)
        except (SyntaxError, UnicodeError) as error:
            return {'status': 'failed', 'syntax_ok': False, 'error': str(error)[:500]}
        test_name = target.name if target.name.startswith('test_') else 'test_' + target.name
        test = target.parent / test_name
        if not test.is_file():
            return {'status': 'skipped', 'syntax_ok': True, 'reason': 'No related test file'}
        executable = Path(sys.executable)
        if executable.name.lower() == 'pythonw.exe':
            executable = executable.with_name('python.exe')
        start = target.parent.relative_to(self.workspace).as_posix()
        # JSON string quoting is not used as shell escaping. Windows uses the
        # single-quoted PowerShell literal form; POSIX uses shlex.quote.
        import os
        quote = (lambda s: "'" + str(s).replace("'", "''") + "'") if os.name == 'nt' else shlex.quote
        command = ('& ' if os.name == 'nt' else '') + quote(str(executable)) + ' -m unittest discover -s ' + quote(start) + ' -p ' + quote(test_name) + ' -v'
        if os.name == 'nt':
            command += '; exit $LASTEXITCODE'
        result = await tools.bash(command, timeout=20)
        return {'status': 'passed' if result['ok'] else 'failed', 'syntax_ok': True, 'test': test_name, **result}
