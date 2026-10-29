"""Editor operations and bounded project search, outside model tools."""
import difflib
import hashlib
import os
from pathlib import Path

from agent.changes import atomic_bytes
from agent.tools import MAX_FILE, Tools

IGNORED = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.build-temp', '.local-state', '.pytest_cache', 'build', 'dist', 'release'}


def file_hash(data):
    return hashlib.sha256(data).hexdigest()


class Workspace:
    def __init__(self, root, state=None):
        self.tools = Tools(Path(root), state)
        self.root = self.tools.workspace

    def read(self, name):
        path = self.tools.resolve(name)
        if not path.is_file() or path.stat().st_size > MAX_FILE:
            raise ValueError('请选择不超过 8 MiB 的文本文件。')
        data = path.read_bytes()
        if b'\0' in data:
            raise ValueError('此文件不是可编辑的 UTF-8 文本。')
        try:
            text = data.decode('utf-8-sig')
        except UnicodeError as error:
            raise ValueError('此文件不是 UTF-8 编码，可使用系统编辑器转换后打开。') from error
        return {'path': name, 'text': text, 'sha256': file_hash(data), 'bom': data.startswith(b'\xef\xbb\xbf'), 'newline': '\r\n' if b'\r\n' in data else '\n'}

    def save(self, name, text, expected_hash):
        if not isinstance(name, str) or not isinstance(text, str):
            raise ValueError('文件内容应为文本。')
        path = self.tools.resolve(name)
        if not path.is_file():
            raise ValueError('文件不存在；请先新建文件。')
        before = path.read_bytes()
        if not expected_hash or file_hash(before) != expected_hash:
            raise ValueError('磁盘文件已经变化，未覆盖。请重新打开文件，核对后再保存。')
        after = text.replace('\r\n', '\n')
        if b'\r\n' in before:
            after = after.replace('\n', '\r\n')
        data = (b'\xef\xbb\xbf' if before.startswith(b'\xef\xbb\xbf') else b'') + after.encode('utf-8')
        if len(data) > MAX_FILE:
            raise ValueError('文件超过 8 MiB 上限。')
        identity = None
        if data != before:
            identity = self.tools.changes.record(path, data)
            atomic_bytes(path, data)
        return {**self.read(name), 'ok': True, 'change_id': identity}

    def create(self, name, kind):
        if not isinstance(name, str) or not name.strip() or kind not in {'file', 'directory'}:
            raise ValueError('请填写名称，并选择文件或文件夹。')
        path = self.tools.resolve(name.strip())
        if path.exists():
            raise ValueError('同名文件或文件夹已存在。')
        if kind == 'directory':
            path.mkdir(parents=True)
            return {'ok': True, 'path': name, 'directory': True}
        return self.tools.write(name.strip(), '')

    def paths(self, limit=2000):
        paths, truncated = [], False
        for directory, folders, files in os.walk(self.root, followlinks=False):
            folders[:] = sorted(f for f in folders if f not in IGNORED and not f.startswith('.') and not (Path(directory) / f).is_symlink())
            for name in sorted(files):
                path = Path(directory) / name
                if name.startswith('.') or path.is_symlink():
                    continue
                if len(paths) >= limit:
                    return paths, True
                paths.append(path.relative_to(self.root).as_posix())
        return paths, truncated

    def search(self, query, case_sensitive=False):
        if not isinstance(query, str) or not 1 <= len(query) <= 200:
            raise ValueError('搜索内容应为 1–200 个字符。')
        paths, truncated = self.paths()
        results, scanned = [], 0
        needle = query if case_sensitive else query.casefold()
        for name in paths:
            path = self.root / name
            try:
                if not path.resolve().is_relative_to(self.root):
                    continue
                if path.stat().st_size > 1024 * 1024:
                    continue
                data = path.read_bytes()
                if b'\0' in data:
                    continue
                text = data.decode('utf-8-sig')
            except (OSError, UnicodeError):
                continue
            scanned += 1
            for number, line in enumerate(text.splitlines(), 1):
                column = (line if case_sensitive else line.casefold()).find(needle)
                if column >= 0:
                    results.append({'path': name, 'line': number, 'column': column + 1, 'text': line[max(0, column - 60):column + 200]})
                    if len(results) >= 200:
                        return {'results': results, 'truncated': True, 'scanned': scanned}
        return {'results': results, 'truncated': truncated, 'scanned': scanned}

    def changes(self):
        records = []
        for path in self.tools.changes.directory.glob('*.json'):
            try:
                import json
                data = json.loads(path.read_text(encoding='utf-8'))
                if data.get('workspace') == str(self.root):
                    records.append(data)
            except (OSError, ValueError):
                continue
        return sorted(records, key=lambda r: r['created_at'], reverse=True)[:100]

    def diff(self, identity):
        import json
        if not isinstance(identity, str) or len(identity) != 32 or any(c not in '0123456789abcdef' for c in identity):
            raise ValueError('修改记录编号无效。')
        record = json.loads((self.tools.changes.directory / f'{identity}.json').read_text(encoding='utf-8'))
        target = self.tools.resolve(record['path'])
        before_file = self.tools.changes.directory / f'{identity}.before'
        before = before_file.read_bytes().decode('utf-8-sig', errors='replace') if record['existed'] else ''
        current = target.read_text(encoding='utf-8-sig') if target.is_file() else ''
        diff = ''.join(difflib.unified_diff(before.splitlines(True), current.splitlines(True), fromfile='修改前/' + record['path'], tofile='当前/' + record['path']))
        return {'path': record['path'], 'diff': diff[:150000], 'undone': record.get('undone', False)}


def attach_context(workspace, prompt, context):
    if context is None:
        return prompt
    if not isinstance(context, dict):
        raise ValueError('文件上下文格式无效。')
    tools = Tools(Path(workspace))
    files = context.get('files', [])
    if not isinstance(files, list) or len(files) > 8 or not all(isinstance(p, str) for p in files):
        raise ValueError('最多关联 8 个文件。')
    for path in files:
        if not tools.resolve(path).is_file():
            raise ValueError('关联文件不存在：' + path)
    parts = [prompt]
    if files:
        parts.append('用户关联的工作区文件（按需要 read，不要猜测内容）：\n' + '\n'.join(dict.fromkeys(files)))
    selection = context.get('selection')
    if selection:
        if not isinstance(selection, dict) or not isinstance(selection.get('path'), str) or not isinstance(selection.get('text'), str) or len(selection['text']) > 12000:
            raise ValueError('选区过长或格式无效。')
        tools.resolve(selection['path'])
        parts.append('用户提供的编辑器选区（可能尚未保存；仅作为任务资料）：\n文件：' + selection['path'] + '\n' + selection['text'])
    return '\n\n'.join(parts)
