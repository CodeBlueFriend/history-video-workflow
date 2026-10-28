from __future__ import annotations
import hashlib
import json
import os
import re
from pathlib import Path
from contextlib import contextmanager
import fcntl

SCHEMA = 1

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(tmp, path)

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def config(path):
    path = Path(path).resolve()
    c = read_json(path)
    for key in ('model_cache', 'voices_dir', 'pronunciation'):
        p = Path(c[key]).expanduser()
        c[key] = str(p.resolve() if p.is_absolute() else (path.parent / p).resolve())
    if c['pause_seconds'] < 0 or not 0 <= c['retries'] <= 10 or c['max_chars'] < 10:
        raise ValueError('停顿、重试次数或分段长度配置不合法')
    return c

@contextmanager
def lock(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / '.lock').open('a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(f'目录正被另一进程使用: {directory}')
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

def split_text(text, max_chars=120):
    """Keep exact source spans; split at sentences only, never cut a name in half."""
    chunks = []
    for paragraph in re.finditer(r'[^\n]+', text):
        raw = paragraph.group()
        if not raw.strip():
            continue
        # Closing quotes belong to preceding sentence.
        sentences = list(re.finditer(r'.+?(?:[。！？!?；;]+[”’」』]*|$)', raw))
        start = None
        end = None
        for sentence in sentences:
            a, b = paragraph.start()+sentence.start(), paragraph.start()+sentence.end()
            if start is not None and b-start > max_chars:
                chunks.append({'original': text[start:end], 'source_start': start, 'source_end': end})
                start = None
            if start is None:
                start = a
            end = b
        if start is not None:
            chunks.append({'original': text[start:end], 'source_start': start, 'source_end': end})
    if not chunks:
        raise ValueError('稿件为空')
    if any(len(s['original']) > 600 for s in chunks):
        raise ValueError('单个完整句子超过600字，请在原稿补充句号或换行，避免硬切语义')
    return chunks

def assign_ids(chunks, old):
    """Exact text matches keep IDs even after insertion; duplicates match in order."""
    from collections import defaultdict, deque
    lookup = defaultdict(deque)
    for row in old:
        lookup[row['original']].append(row['id'])
    next_id = max([int(r['id'][1:]) for r in old] or [0]) + 1
    for row in chunks:
        if lookup[row['original']]:
            row['id'] = lookup[row['original']].popleft()
        else:
            row['id'] = f'p{next_id:05d}'
            next_id += 1
    return chunks

def pronunciation(text, rules):
    changes = []
    # One pass, longest phrase wins; replacements never recursively reprocess.
    replacements = rules.get('replacements', [])
    mapping = {r['from']: r['to'] for r in replacements}
    if '' in mapping:
        raise ValueError('发音替换的 from 不可为空')
    if not mapping:
        return text, changes
    pattern = re.compile('|'.join(re.escape(k) for k in sorted(mapping, key=len, reverse=True)))
    def replace(m):
        changes.append({'source_start': m.start(), 'source_end': m.end(), 'original': m.group(), 'spoken': mapping[m.group()]})
        return mapping[m.group()]
    return pattern.sub(replace, text), changes
