"""Storyline history and conservative duplicate checks; characters may recur."""
from __future__ import annotations
import copy
import re
import unicodedata
from .core import require, read, write, now, exclusive

HISTORY_FILE = '01_选题库/故事线历史.json'
FIELDS = ('storyline_id', 'core_event', 'conflict', 'outcome')


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text).lower() if c.isalnum())


def profile(data):
    require(isinstance(data, dict), '需要story故事线档案；不能只凭标题查重')
    for key in FIELDS:
        require(isinstance(data.get(key), str) and normalize(data[key]), '故事线缺少 ' + key)
    for key in ('characters', 'turning_points'):
        require(isinstance(data.get(key), list) and data[key] and
                all(isinstance(x, str) and normalize(x) for x in data[key]), '故事线缺少有效的 ' + key)
    aliases = data.get('aliases', [])
    require(isinstance(aliases, list) and all(isinstance(x, str) and normalize(x) for x in aliases), '故事线aliases必须是编号/事件别名数组')
    require(isinstance(data.get('distinctness_note', ''), str), 'distinctness_note必须是区别说明文本')
    return copy.deepcopy(data)


def history(root):
    path = root / HISTORY_FILE
    rows = read(path) if path.exists() else []
    require(isinstance(rows, list), '故事线历史必须为数组')
    rows = copy.deepcopy(rows)
    covered = {r.get('episode') for r in rows}
    missing = []
    for path in sorted(root.glob('EP*/00_项目记录/工作台状态.json')):
        state = read(path)
        if not state.get('storyline'):
            if state['episode'] not in covered:
                missing.append(state['episode'])
            continue
        status = 'ACCEPTED' if state.get('accepted') else ('EXPORTED' if state.get('export') else 'IN_PRODUCTION')
        rows.append({'id': state['episode'], 'episode': state['episode'], 'title': state['title'],
                     'status': status, 'story': state['storyline'], 'source': str(path)})
        for i, old in enumerate(state.get('storyline_history', []), 1):
            rows.append({'id': f'{state["episode"]}#previous-{i}', 'episode': state['episode'],
                         'title': state['title'], 'status': 'PREVIOUS_STORYLINE', 'story': old['story']})
    return {'records': rows, 'unprofiled_episodes': missing,
            'note': '人物重复允许；同一核心事件、冲突与情节发展的重复需排除。未补录的旧集无法完整查重。'}


def event_keys(p):
    return {normalize(x) for x in [p['storyline_id'], p['core_event'], *p.get('aliases', [])]}


def plot_text(p):
    return ''.join(normalize(x) for x in [p['core_event'], p['conflict'], *p['turning_points'], p['outcome']])


def similarity(a, b):
    def grams(s):
        return {s[i:i+3] for i in range(max(1, len(s)-2))}
    x, y = grams(a), grams(b)
    return 2*len(x & y)/(len(x)+len(y))


def compare(candidate, rows):
    duplicates, possible = [], []
    for row in rows:
        old = profile(row['story'])
        identity = {k: row.get(k) for k in ('id', 'episode', 'title', 'status')}
        score = similarity(plot_text(candidate), plot_text(old))
        if event_keys(candidate) & event_keys(old) or plot_text(candidate) == plot_text(old):
            duplicates.append({**identity, 'reason': '故事线编号/事件/别名相同，或冲突与情节完全相同'})
        elif score >= .55:
            possible.append({**identity, 'similarity': round(score, 3), 'reason': '情节文字相近，需核对是否只是换标题、换视角或换措辞'})
    return duplicates, possible


def check(root, data, exclude_episode=None, extra_records=()):
    candidate = profile(data)
    ledger = history(root)
    rows = [r for r in ledger['records'] if r.get('episode') != exclude_episode] if exclude_episode else ledger['records']
    duplicates, possible = compare(candidate, [*rows, *extra_records])
    return {'status': 'DUPLICATE' if duplicates else ('REVIEW_REQUIRED' if possible else 'NO_MATCH_FOUND'),
            'duplicates': duplicates, 'possible_matches': possible,
            'unprofiled_episodes': [e for e in ledger['unprofiled_episodes'] if e != exclude_episode],
            'distinctness_note': candidate.get('distinctness_note', ''),
            'limitation': '本地规则与文字相似度不能保证识别语义改写；选题审核仍须阅读历史档案对比情节，不按人物姓名去重。'}


def ensure_distinct(result):
    require(not result['duplicates'], '故事线重复：' + '、'.join(r['title'] or r['id'] for r in result['duplicates']) + '；请更换核心故事，已有故事的返修请继续原项目')
    require(not result['possible_matches'] or result['distinctness_note'].strip(),
            '发现疑似重复故事线；请核对历史后在story.distinctness_note说明核心事件、冲突和转折的实质区别')


def record(root, data):
    require(isinstance(data, dict), '历史记录需要对象')
    for key in ('id', 'title', 'status', 'evidence'):
        require(isinstance(data.get(key), str) and data[key].strip(), '历史记录缺少 ' + key)
    require('episode' not in data or (isinstance(data['episode'], str) and re.fullmatch(r'EP\d+_[^/\\]+', data['episode'])),
            'episode需要有效集名，例如EP001_本集标题')
    data = {**copy.deepcopy(data), 'story': profile(data.get('story')), 'recorded_at': now()}
    with exclusive(root):
        path = root / HISTORY_FILE
        rows = read(path) if path.exists() else []
        require(not any(r['id'] == data['id'] for r in rows), '历史记录编号已存在；保留原记录，补充内容使用新编号')
        rows.append(data)
        write(path, rows)
    return {'saved': str(path), 'id': data['id']}


def set_profile(episode, data, reason=None):
    candidate = profile(data)
    result = check(episode.root, candidate, exclude_episode=episode.s['episode'])
    ensure_distinct(result)
    episode.editable(reason)
    if episode.s.get('storyline'):
        episode.s.setdefault('storyline_history', []).append({'story': copy.deepcopy(episode.s['storyline']), 'time': now()})
    episode.s['storyline'] = candidate
    if episode.s.get('creative_brief', {}).get('selected'):
        episode.s['creative_brief']['selected']['story'] = copy.deepcopy(candidate)
    episode.s['storyline_check'] = {**result, 'checked_at': now()}
    episode.invalidate('evidence')
    episode.s['stage_reviews'] = {}
    return episode.save('补录/修改故事线档案；重开理由：' + (reason or '未锁稿'))
