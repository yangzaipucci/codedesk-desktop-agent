"""Opt-out feature gates and bounded, non-secret patch metadata."""
import json
import os
from pathlib import Path
import time

FEATURES = ('skills', 'custom', 'hooks', 'autotest', 'reviewer', 'daemon')
DEFAULT_PROFILE = 'skills'


def default_enabled(name):
    return name == 'skills' or DEFAULT_PROFILE == 'all' or DEFAULT_PROFILE == 'custom' and name != 'daemon'


def enabled(name, directory=None):
    if os.environ.get('CODEDESK_LEGACY', '').lower() in {'1', 'true'}:
        return False
    if name in {'hooks', 'autotest', 'reviewer'} and not enabled('custom', directory):
        return False
    override = os.environ.get('ENABLE_' + name.upper())
    if override is not None:
        return override.lower() not in {'0', 'false', 'off'}
    try:
        value = json.loads((Path(directory) / 'settings.json').read_text(encoding='utf-8'))
        return value.get('enable_' + name, default_enabled(name)) is not False
    except (OSError, ValueError, TypeError):
        return default_enabled(name)


def assets():
    import sys
    return (Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]) / 'agent_assets'


def token_bound(text):
    """UTF-8 byte count is a conservative byte-token upper bound, not billing."""
    return len(text.encode('utf-8'))


def truncate(text, budget):
    return text.encode('utf-8')[:max(0, budget)].decode('utf-8', errors='ignore')


def file_retry(operation):
    """Bounded retry for transient Windows sharing/antivirus file locks."""
    for attempt in range(10):
        try:
            return operation()
        except PermissionError:
            if os.name != 'nt' or attempt == 9:
                raise
            time.sleep(.02 * (attempt + 1))


def read_json(path):
    return json.loads(file_retry(lambda: Path(path).read_text(encoding='utf-8')))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    file_retry(lambda: temporary.replace(path))


def project_guidance(workspace, directory, budget=350):
    if not enabled('custom', directory):
        return '', []
    global_file = Path(directory) / 'AGENTS.md'
    if not global_file.is_file():
        global_file = assets() / 'AGENTS.md'
    text, sources = '', []
    project_file = Path(workspace) / 'AGENTS.md'
    for label, path in [('global', global_file), ('project', project_file)]:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 32768:
            continue
        body = path.read_text(encoding='utf-8-sig')
        prefix = f'\n[{label} AGENTS.md]\n'
        available = max(0, budget - token_bound(text))
        if label=='global' and project_file.is_file():
            available = min(120, available)
        piece = truncate(prefix + body, available)
        text += piece
        sources.append({'layer': label, 'loaded': True, 'line_count':len(body.splitlines()), 'injected_bytes':token_bound(piece), 'truncated': piece != prefix + body})
    return text, sources
