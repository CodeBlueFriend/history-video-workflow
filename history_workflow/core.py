from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import wave
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / 'reference' / '历史故事长篇'
ROLES = ('evidence', 'outline', 'fact', 'narrative', 'oral', 'coherence', 'clean')
SCORES = {'accuracy': 30, 'causality': 20, 'structure': 20, 'oral': 15, 'originality': 10, 'title': 5}
CAPS = ('original_audio', 'motion_crop', 'transitions', 'subtitle_correction', 'long_video', 'archive', 'short_sample', 'single_image_test')
FINAL_CHECKS = ('content', 'audio', 'subtitles', 'identity', 'cover', 'motion', 'transitions', 'full_playback', 'archive_restore')

class WorkflowError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise WorkflowError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.pending-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def inside(root, relative):
    root = Path(root).resolve()
    p = (root / relative).resolve()
    require(p.is_relative_to(root), '路径越出项目目录')
    return p


def desktop():
    if sys.platform == 'win32':
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as k:
            return Path(os.path.expandvars(winreg.QueryValueEx(k, 'Desktop')[0]))
    if sys.platform == 'darwin':
        result = subprocess.run(['osascript', '-e', 'POSIX path of (path to desktop folder)'], capture_output=True, text=True, check=True)
        return Path(result.stdout.strip())
    config = Path.home() / '.config/user-dirs.dirs'
    if config.exists():
        match = re.search(r'^XDG_DESKTOP_DIR="([^"]+)"', config.read_text(), re.M)
        if match:
            return Path(match[1].replace('$HOME', str(Path.home())))
    raise WorkflowError('无法识别真实桌面，请在 init 使用 --output-dir 指定生产资料输出目录')


def default_root():
    return Path(__file__).resolve().parents[1] / 'production'


def initialize(root, output_dir=None):
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    require(TEMPLATE.exists(), '缺少 reference/历史故事长篇 模板目录')
    for source in TEMPLATE.rglob('*'):
        target = inside(root, source.relative_to(TEMPLATE))
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif not target.exists():
            shutil.copy2(source, target)
    config = root / '00_项目配置/工作台配置.json'
    if not config.exists():
        write(config, {'schema': 5, 'root': str(root), 'created': now(), 'integrations': {'writer': 'NOT_CONNECTED', 'research': 'NOT_CONNECTED', 'reviewer': 'MANUAL_IMPORT', 'tts': 'MINIMAX_WEB_MANUAL', 'editor': 'NOT_VERIFIED'}})
    settings = read(config)
    settings['root'] = str(root)
    if output_dir is not None:
        output = Path(output_dir).expanduser().resolve()
        require(not output.is_relative_to(root) and not root.is_relative_to(output), '生产资料输出目录必须与项目运行目录分开')
        settings['output_dir'] = str(output)
    write(config, settings)
    return {'root': str(root), 'output_dir': settings.get('output_dir'), 'config': str(config)}


@contextmanager
def exclusive(root):
    """OS-owned lock is released on process exit, including crashes."""
    p = Path(root) / '.workflow.lock'
    with p.open('a+b') as f:
        if os.name == 'nt':
            import msvcrt
            f.seek(0); f.write(b'0'); f.flush(); f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == 'nt':
                f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def new_episode(root, title, minimum=1800, maximum=1860, brief=None, story=None, production_kind='FORMAL'):
    require(production_kind in ('FORMAL', 'SAMPLE'), 'production_kind须为FORMAL或SAMPLE')
    require(title and not re.search(r'[/\\<>:"|?*\x00-\x1f]', title) and title not in ('.', '..'), '选题名含非法字符')
    require(0 < minimum <= maximum and math.isfinite(maximum), '时长区间无效')
    root = Path(root)
    require((root / '00_项目配置/工作台配置.json').exists(), '请先 init')
    with exclusive(root):
        if story is None and brief is not None:
            story = brief.get('selected', {}).get('story')
        story_check = None
        if story is not None:
            from .story_history import profile, check, ensure_distinct
            story = profile(story)
            story_check = check(root, story)
            if production_kind != 'SAMPLE':
                ensure_distinct(story_check)
            else:
                story_check = {'status': 'EXCLUDED_SAMPLE'}
        ids = [int(m.group(1)) for p in root.iterdir() if (m := re.match(r'EP(\d+)_', p.name))]
        name = f'EP{max(ids, default=0)+1:03d}_{title}'
        target = inside(root, name)
        staging = root / ('.new-' + uuid.uuid4().hex)
        shutil.copytree(root / 'EP000_模板', staging)
        state = {'schema': 5, 'episode': name, 'title': title, 'revision': 0, 'status': 'NEW', 'range': [minimum, maximum], 'sources': {}, 'claims': {}, 'timeline': [], 'disputes': [], 'outline': '', 'script': None, 'reviews': {}, 'issues': {}, 'lock': None, 'estimate': None, 'audio_tasks': [], 'assets': {}, 'plan': None, 'documents': [], 'handoff': None, 'export': None, 'accepted': None, 'events': []}
        if brief is not None:
            state['creative_brief'] = copy.deepcopy(brief)
        state['production_kind'] = production_kind
        if story is not None:
            state['storyline'] = story
            state['storyline_check'] = {**story_check, 'checked_at': now()}
        state['editing_defaults'] = read(root / '00_项目配置/剪辑规则配置.json')
        from .covers import config as cover_config
        state['cover_plan'] = cover_config(root)
        from .writing import config as writing_config
        state['writing_rules'] = writing_config(root)
        write(staging / '00_项目记录/工作台状态.json', state)
        staging.rename(target)
    return {'episode': name, 'path': str(target), 'storyline_check': story_check or {'status': 'MISSING_PROFILE'}}


def duration(path, video=False):
    path = Path(path)
    if path.suffix.lower() == '.wav' and not video:
        with wave.open(str(path), 'rb') as w:
            value = w.getnframes() / w.getframerate()
    else:
        require(shutil.which('ffprobe'), '需要 ffprobe 测量此格式（仅探测，不渲染）')
        r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_type,width,height', '-of', 'json', str(path)], capture_output=True, text=True, check=True)
        data = json.loads(r.stdout)
        types = {s['codec_type'] for s in data['streams']}
        require('video' in types if video else 'audio' in types, '文件缺少所需媒体流')
        if video:
            require('audio' in types, '成片缺少音轨')
        value = float(data['format']['duration'])
    require(math.isfinite(value) and value > 0, '媒体时长无效')
    return value


def effective(text, readings=None):
    for old, new in sorted((readings or {}).items(), key=lambda x: -len(x[0])):
        text = text.replace(old, new)
    require(not re.search(r'[0-9A-Za-z]', text), '数字/缩写须在 readings 提供计划读法后计数')
    return len(re.findall(r'[\u3400-\u9fff]', text))


def estimate(text, config):
    rate = float(config['rate'])
    require(math.isfinite(rate) and rate > 0, '语速必须为正数')
    pause = float(config.get('extra_pause', 0))
    intro = float(config.get('net_intro_outro', 0))
    require(all(math.isfinite(v) and v >= 0 for v in (pause, intro)), '额外时长无效')
    require(not pause or config.get('pause_excluded_from_sample') is True, '额外停顿需明确未计入样音语速')
    n = effective(text, config.get('readings'))
    audio = n / rate * 60 + pause
    return {'characters': n, 'rate': rate, 'basis': 'ASSUMED', 'audio_seconds': audio, 'video_seconds': audio + intro, 'config': config}


class Episode:
    def __init__(self, root, name):
        require(re.fullmatch(r'EP\d+_[^/\\]+', name) is not None and not name.startswith('EP000_'), '无效集名')
        self.root = Path(root).resolve()
        self.path = inside(self.root, name)
        self.state_path = self.path / '00_项目记录/工作台状态.json'
        require(self.state_path.exists(), '本集未初始化')
        self.s = read(self.state_path)
        self.s.setdefault('stage_reviews', {})

    def save(self, action):
        self.s['revision'] += 1
        self.s['events'].append({'time': now(), 'action': action, 'revision': self.s['revision']})
        # The authoritative state is a single atomic file. Orphaned snapshots are harmless.
        write(self.path / f'00_项目记录/历史版本/state_{self.s["revision"]:05d}_{uuid.uuid4().hex[:8]}.json', self.s)
        write(self.state_path, self.s)
        return {'episode': self.s['episode'], 'status': self.s['status'], 'revision': self.s['revision']}

    def signature(self):
        payload = {k: self.s[k] for k in ('sources', 'claims', 'timeline', 'disputes', 'outline', 'script')}
        if 'creative_brief' in self.s:
            payload['creative_brief'] = self.s['creative_brief']
        if 'storyline' in self.s:
            payload['storyline'] = self.s['storyline']
        if 'writing_rules' in self.s:
            payload['writing_rules'] = self.s['writing_rules']
        return digest(payload)

    def require_locked(self):
        require(self.s['lock'] and self.s['lock']['input_hash'] == self.signature(), '需要当前资料与文稿通过审核并锁稿')
        require(self.s['estimate'] and self.s['estimate'].get('in_range') and self.s['estimate'].get('input_hash') == self.signature(), '当前时长估算未达标')
        require(self.s['lock'].get('stage_reviews_hash', digest(self.s['stage_reviews'])) == digest(self.s['stage_reviews']), '前置审核在锁稿后变化，需要重新锁稿')
        require(self.s['lock']['reviews_hash'] == digest(self.s['reviews']) and self.s['lock']['issues_hash'] == digest(self.s['issues']), '锁稿后审核或问题记录已变化，需要重新锁稿')

    def invalidate(self, kind):
        self.s['handoff'] = self.s['export'] = self.s['accepted'] = None
        if kind in ('script', 'evidence'):
            self.s['lock'] = None
            self.s['reviews'] = {}
            self.s['estimate'] = None
            self.s['audio_tasks'] = []
            self.s['plan'] = None
            for asset in self.s['assets'].values():
                asset['stale'] = True
            self.s['status'] = 'DRAFTING'
        elif kind == 'audio':
            self.s['plan'] = None
            self.s['status'] = 'AUDIO_REVIEW' if any(a['kind'] == 'audio' and not a['stale'] for a in self.s['assets'].values()) else 'WAITING_WEB_AUDIO'
        else:
            self.s['status'] = 'SCRIPT_LOCKED' if self.s['lock'] else 'DRAFTING'

    def editable(self, confirmation):
        require(not self.s['lock'] or confirmation, '已锁稿。修改将使审核、配音、字幕和剪辑失效；确认影响后使用 --reopen-reason 记录重开理由')

    def content(self, kind, data, confirmation=None):
        self.editable(confirmation)
        if kind == 'source':
            for key in ('id', 'title', 'genre', 'locator', 'excerpt', 'access', 'obtained_at'):
                require(data.get(key), f'来源缺少 {key}')
            require(re.fullmatch(r'SRC\d+', data['id']), '来源编号格式 SRC001')
            require(data['access'] in ('READ', 'USER_PROVIDED', 'UNREAD', 'RESTRICTED'), '来源 access 无效')
            self.s['sources'][data['id']] = data
        elif kind == 'claim':
            for key in ('id', 'text', 'sources', 'reliability', 'allowed_expression', 'reason'):
                require(data.get(key), f'主张缺少 {key}')
            require(re.fullmatch(r'C\d+', data['id']), '主张编号格式 C001')
            require(all(x in self.s['sources'] for x in data['sources']), '主张引用未知来源')
            require(data['reliability'] in ('SUPPORTED', 'LIMITED', 'DISPUTED', 'UNVERIFIED'), '可靠程度无效')
            self.s['claims'][data['id']] = data
        elif kind in ('timeline', 'disputes'):
            require(isinstance(data, list), '需要 JSON 数组')
            self.s[kind] = data
        elif kind == 'outline':
            require(isinstance(data, str) and data.strip(), '大纲不能为空')
            self.s['outline'] = data
        elif kind == 'script':
            for key in ('text', 'author'):
                require(data.get(key), f'文稿缺少 {key}')
            paragraphs = [p.strip() for p in re.split(r'\n\s*\n', data['text']) if p.strip()]
            require(paragraphs and '此处填写' not in data['text'], '不能采用空白占位模板')
            data = {**data, 'version': (self.s['script'] or {}).get('version', 0)+1, 'paragraphs': [{'id': f'P{i:03d}', 'text': p} for i,p in enumerate(paragraphs, 1)]}
            self.s['script'] = data
        else:
            raise WorkflowError('未知内容类型')
        self.invalidate('script' if kind == 'script' else 'evidence')
        if kind == 'outline':
            self.s['status'] = 'OUTLINE_REVIEW'
        elif kind != 'script':
            self.s['status'] = 'EVIDENCE_REVIEW' if self.s['sources'] and self.s['claims'] else 'RESEARCHING'
        return self.save(f'{kind} 更新；重开理由：{confirmation or "未锁稿"}')

    def stage_signature(self, role):
        require(role in ('evidence', 'outline'), '前置审核仅支持 evidence 或 outline')
        keys = ('sources', 'claims', 'timeline', 'disputes')
        if role == 'outline':
            keys += ('outline',)
        payload = {k:self.s[k] for k in keys}
        if 'creative_brief' in self.s:
            payload['creative_brief'] = self.s['creative_brief']
        if 'storyline' in self.s:
            payload['storyline'] = self.s['storyline']
        if 'writing_rules' in self.s:
            payload['writing_rules'] = self.s['writing_rules']
        return digest(payload)

    def stage_packet(self, role):
        packet = {k:self.s[k] for k in ('sources', 'claims', 'timeline', 'disputes')}
        if role == 'outline':
            packet['outline'] = self.s['outline']
        packet['creative_brief'] = self.s.get('creative_brief', {})
        packet['storyline'] = self.s.get('storyline')
        packet['writing_rules'] = self.s.get('writing_rules', {})
        packet.update(role=role, input_hash=self.stage_signature(role), instruction='只审核资料可追溯性、主张边界或提纲结构；不对尚未生成的稿件评分。')
        path = self.path / f'03_审核记录/独立任务/{role}_前置_{packet["input_hash"][:12]}.json'
        write(path, packet)
        return {'packet':str(path), 'input_hash':packet['input_hash']}

    def stage_review(self, data):
        role = data.get('role')
        require(data.get('input_hash') == self.stage_signature(role), '前置审核版本不匹配')
        require(data.get('reviewer') and data.get('evidence') and data.get('conclusion') in ('PASS','FAIL') and isinstance(data.get('issues'),list), '前置审核记录不完整')
        require(not (data['conclusion']=='PASS' and data['issues']), '前置审核仍有问题不能放行')
        require(self.s['sources'] and self.s['claims'], '缺少来源或主张')
        if role == 'outline':
            require(self.s['outline'], '缺少提纲')
            prior = self.s['stage_reviews'].get('evidence', {})
            require(prior.get('conclusion')=='PASS' and prior.get('input_hash')==self.stage_signature('evidence'), '须先完成当前资料审核')
        self.s['stage_reviews'][role] = data
        self.s['status'] = ('OUTLINE_REVIEW' if role=='evidence' else 'DRAFTING') if data['conclusion']=='PASS' else 'BLOCKED'
        return self.save('前置独立审核 ' + role)

    def review_packet(self, role):
        require(role in ROLES and self.s['script'], '需要文稿与有效审核角色')
        packet = {'role': role, 'title': self.s['script'].get('title', self.s['title']), 'input_hash': self.signature(), 'script': self.s['script']['text'], 'paragraphs': self.s['script']['paragraphs'], 'sources': self.s['sources'], 'claims': self.s['claims'], 'timeline': self.s['timeline'], 'disputes': self.s['disputes'], 'outline': self.s['outline'], 'rubric': SCORES, 'instruction': '独立核对；结论、证据、逐项量表、问题必须实际填写。不得读取作者自评。'}
        packet['creative_brief'] = self.s.get('creative_brief', {})
        packet['storyline'] = self.s.get('storyline')
        packet['writing_rules'] = self.s.get('writing_rules', {})
        path = self.path / f'03_审核记录/独立任务/{role}_{self.signature()[:12]}.json'
        write(path, packet)
        return {'packet': str(path), 'input_hash': self.signature()}

    def review(self, data):
        require(self.s['script'], '尚无文稿')
        require(data.get('role') in ROLES and data.get('input_hash') == self.signature(), '审核角色或输入版本不匹配')
        require(data.get('reviewer') and data['reviewer'] != self.s['script']['author'], '审稿人与作者必须分离')
        require(data.get('evidence') and data.get('conclusion') in ('PASS', 'FAIL') and isinstance(data.get('issues'), list), '缺少实审依据、结论或问题数组')
        scores = data.get('scores', {})
        require(set(scores) == set(SCORES), '必须填写六维评分')
        for key, maximum in SCORES.items():
            v = scores[key]
            require(isinstance(v, dict) and isinstance(v.get('score'), (int, float)) and 0 <= v['score'] <= maximum and v.get('reason'), f'{key} 评分/理由无效')
        if data['role'] == 'coherence':
            require(all(data.get('checks', {}).get(k) for k in ('time', 'identity', 'knowledge', 'causality', 'transition', 'repetition', 'promise')), '缺少整稿连贯性逐项复检')
        for issue in data['issues']:
            for key in ('id', 'paragraph', 'quote', 'severity', 'description', 'evidence', 'repair', 'acceptance'):
                require(issue.get(key), f'问题缺少 {key}')
            references = issue['paragraph'].split('/') if isinstance(issue['paragraph'], str) else []
            require(references and all(ref in {p['id'] for p in self.s['script']['paragraphs']} for ref in references), '问题段落不存在')
            require(issue['severity'] in ('P0', 'P1', 'P2', 'P3') and isinstance(issue.get('factual'), bool), '问题严重度/事实标记无效')
            old = self.s['issues'].get(issue['id'])
            if old:
                require(old['severity'] == issue['severity'] and old['factual'] == issue['factual'], '不得降低既有问题等级或事实标记')
            self.s['issues'][issue['id']] = {**issue, 'version': self.s['script']['version'], 'history': (old or {}).get('history', []), 'status': 'OPEN'}
        self.s['reviews'][data['role']] = data
        self.s['status'] = 'REVIEWING'
        return self.save('导入独立审核 ' + data['role'])

    def resolve(self, data):
        require(data.get('id') in self.s['issues'], '未知问题')
        issue = self.s['issues'][data['id']]
        require(data.get('input_hash') == self.signature(), '复审输入版本不匹配')
        require(data.get('reviewer') and data['reviewer'] != self.s['script']['author'] and data.get('evidence'), '缺少独立复审人与依据')
        outcome = data.get('outcome')
        require(outcome in ('FIXED', 'FAILED', 'ACCEPTED', 'RETAINED'), '复审结果无效')
        if outcome == 'ACCEPTED':
            require(issue['severity'] == 'P1' and not issue['factual'] and data.get('user_acceptance'), '仅非事实性 P1 可由用户逐项接受')
        if outcome == 'RETAINED':
            require(issue['severity'] in ('P2', 'P3') and not issue['factual'] and data.get('reason'), '保留问题需要理由且不能有事实硬伤')
        if outcome == 'FIXED':
            require(data.get('before') and data.get('after') and data.get('repair'), '修复需记录修改前后及动作')
        failed = sum(h['outcome'] == 'FAILED' for h in issue['history'])
        require(failed < 2 or data.get('user_decision'), '两轮返修失败，需记录用户裁决，禁止继续自动循环')
        issue['history'].append({**data, 'time': now()})
        issue['status'] = outcome
        if outcome == 'FAILED' and failed >= 1:
            self.s['status'] = 'BLOCKED_USER_DECISION'
        return self.save('问题复审 ' + data['id'])

    def timing(self, config):
        require(self.s['script'], '尚无文稿')
        result = estimate(self.s['script']['text'], config)
        if config.get('sample_file'):
            require(config.get('sample_text') and config.get('voice') and config.get('settings'), '校准需要样音文字、已选音色与网页设置')
            sample = Path(config['sample_file']).resolve()
            seconds = duration(sample)
            rate = effective(config['sample_text'], config.get('readings')) / seconds * 60
            result = estimate(self.s['script']['text'], {**config, 'rate': rate})
            stored = self.copy_asset(sample, '校准')
            result.update(basis='MEASURED_SAMPLE', sample={**stored, 'seconds': seconds})
        result['input_hash'] = self.signature()
        result['in_range'] = self.s['range'][0] <= result['video_seconds'] <= self.s['range'][1]
        self.s['estimate'] = result
        self.s['handoff'] = self.s['export'] = self.s['accepted'] = None
        self.save('文稿时长估算')
        return result

    def blockers(self):
        errors = []
        s = self.s
        if not s['script'] or not s['outline'] or not s['sources'] or not s['claims']:
            errors.append('缺少文稿、大纲、来源或主张')
        for c in s['claims'].values():
            if c['reliability'] == 'UNVERIFIED' or not c.get('paragraphs'):
                errors.append(c['id'] + ' 未核实或未映射段落')
            if s['script'] and not set(c.get('paragraphs', [])) <= {p['id'] for p in s['script']['paragraphs']}:
                errors.append(c['id'] + ' 引用未知段落')
            for sid in c['sources']:
                if s['sources'][sid]['access'] not in ('READ', 'USER_PROVIDED'):
                    errors.append(sid + ' 未实际取得来源')
        for role in ROLES:
            if role in ('evidence', 'outline'):
                stage = s['stage_reviews'].get(role, {})
                if stage.get('input_hash') == self.stage_signature(role) and stage.get('conclusion') == 'PASS':
                    continue
            r = s['reviews'].get(role, {})
            if r.get('input_hash') != self.signature() or r.get('conclusion') != 'PASS' or sum(x['score'] for x in r.get('scores', {}).values()) < 85:
                errors.append(role + ' 缺少当前版本合格审核')
        for issue in s['issues'].values():
            history = issue['history']
            valid = history and history[-1]['input_hash'] == self.signature()
            if issue['severity'] != 'P3' or issue['factual']:
                if not valid or issue['status'] not in ('FIXED', 'ACCEPTED', 'RETAINED'):
                    errors.append(issue['id'] + ' 尚未完成当前版本复审')
        e = s['estimate'] or {}
        if e.get('input_hash') != self.signature() or not e.get('in_range'):
            errors.append('文稿时长估算未达标')
        return errors

    def lock(self):
        if self.s.get('storyline') and self.s.get('production_kind') != 'SAMPLE':
            from .story_history import check, ensure_distinct
            ensure_distinct(check(self.root, self.s['storyline'], exclude_episode=self.s['episode']))
        errors = self.blockers()
        require(not errors, '锁稿阻断：' + '；'.join(errors))
        self.s['lock'] = {'input_hash': self.signature(), 'script_hash': digest(self.s['script']), 'time': now(), 'reviews_hash': digest(self.s['reviews']), 'issues_hash': digest(self.s['issues']), 'stage_reviews_hash': digest(self.s['stage_reviews'])}
        self.s['status'] = 'SCRIPT_LOCKED'
        write(self.path / '02_故事文稿/口播定稿.txt', self.s['script']['text'])
        self.save('锁稿')
        return self.document('PLAN')

    def copy_asset(self, source, category):
        source = Path(source).expanduser().resolve()
        require(source.is_file() and source.stat().st_size > 0, '素材文件不存在或为空')
        h = file_hash(source)
        target = inside(self.path, Path('04_素材') / category / f'{h[:16]}_{source.name}')
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)
        require(file_hash(target) == h, '素材副本校验失败')
        return {'path': str(target.relative_to(self.path)), 'sha256': h}

    def receive_audio(self, data):
        """Receive a user-produced full-script recording without inventing TTS settings."""
        self.require_locked()
        require(not self.s['audio_tasks'], '已有配音任务；请使用 asset 按现有编号导入，避免覆盖对应关系')
        require(data.get('confirmed_mapping') is True, '请确认上传录音对应本集完整锁稿，内容仍需试听验收')
        require(data.get('source') and data.get('rights'), '缺少素材来源与使用条件')
        duration(data['file'])  # Validate before adding the task.
        self.s['audio_tasks'] = [{
            'id': 'A001', 'paragraphs': [p['id'] for p in self.s['script']['paragraphs']],
            'original': self.s['script']['text'], 'spoken': self.s['script']['text'],
            'voice': data.get('voice'), 'settings': data.get('settings'),
            'metadata_status': 'USER_PROVIDED' if data.get('voice') and data.get('settings') else 'PENDING_CONFIRMATION',
            'origin': 'USER_FULL_SCRIPT_RECORDING', 'script_hash': self.s['lock']['script_hash']
        }]
        return self.asset({**data, 'kind': 'audio', 'id': 'A001'})

    def audio_package(self, config):
        self.require_locked()
        require(config.get('voice') and config.get('settings'), '请记录已选音色及实际网页设置')
        if self.s['estimate']['basis'] == 'MEASURED_SAMPLE':
            calibrated = self.s['estimate']['config']
            require(config['voice'] == calibrated['voice'] and config['settings'] == calibrated['settings'], '音色或网页设置与实测校准不同，须重新校准')
        limit = config.get('limit')
        require(isinstance(limit, int) and limit > 0, '请填写当前网页字数上限')
        tasks = []
        fixes = config.get('pronunciation', {})
        for p in self.s['script']['paragraphs']:
            text = p['text']
            pattern = '|'.join(re.escape(x) for x in sorted(fixes, key=len, reverse=True))
            spoken = re.sub(pattern, lambda m: fixes[m.group()], text) if pattern else text
            # Splitting is explicit and lossless; paragraph mapping remains many-to-many.
            for start in range(0, len(spoken), limit):
                aid = f'A{len(tasks)+1:03d}'
                tasks.append({'id': aid, 'paragraphs': [p['id']], 'original': text, 'spoken': spoken[start:start+limit], 'voice': config['voice'], 'settings': config['settings'], 'script_hash': self.s['lock']['script_hash']})
        package_hash = digest(tasks)
        if self.s['audio_tasks'] and digest(self.s['audio_tasks']) == package_hash:
            return {'tasks': len(tasks), 'reused': True}
        self.invalidate('audio')
        for a in self.s['assets'].values():
            if a['kind'] == 'audio':
                a['stale'] = True
        self.s['audio_tasks'] = tasks
        folder = self.path / f'04_素材/音频/网页文本包/{package_hash[:12]}'
        for task in tasks:
            write(folder / (task['id'] + '.txt'), task['spoken'])
        write(folder / '任务映射.json', tasks)
        write(folder / '字幕原文.txt', self.s['script']['text'])
        self.save('准备网页配音包')
        return {'tasks': len(tasks), 'folder': str(folder)}

    def asset(self, data):
        self.require_locked()
        kind = data.get('kind')
        require(kind in ('audio', 'image', 'cover', 'music', 'sfx'), '未知素材类型')
        prefixes = {'audio': 'A', 'image': 'IMG', 'cover': 'COVER', 'music': 'M', 'sfx': 'FX'}
        require(re.fullmatch(prefixes[kind] + r'\d+', data.get('id', '')), '素材编号不匹配')
        require(data.get('source') and data.get('rights'), '缺少素材来源与使用条件')
        require(data.get('confirmed_mapping') is True, '必须明确确认素材编号，不能按下载顺序猜测')
        if kind == 'audio':
            require(data['id'] in {x['id'] for x in self.s['audio_tasks']}, '未知配音任务编号')
            measured = {'seconds': duration(data['file'])}
        elif kind in ('image', 'cover'):
            from PIL import Image
            with Image.open(data['file']) as image:
                image.verify()
            with Image.open(data['file']) as image:
                measured = {'width': image.width, 'height': image.height}
            if kind == 'cover' and data.get('cover_target'):
                from .covers import validate, config as cover_config
                measured['cover_validation'] = validate(self.s.get('cover_plan') or cover_config(self.root), data['cover_target'], measured['width'], measured['height'])
            if kind == 'image':
                require(data.get('scene') and data.get('paragraphs'), '图片需关联单一代表场景和段落')
                require(set(data['paragraphs']) <= {p['id'] for p in self.s['script']['paragraphs']}, '图片引用未知段落')
        else:
            measured = {'seconds': duration(data['file'])}
        stored = self.copy_asset(data['file'], {'audio': '音频/网页下载文件', 'image': '图片/原图', 'cover': '封面/导出封面', 'music': '音乐与音效', 'sfx': '音乐与音效'}[kind])
        asset = {k: v for k,v in data.items() if k != 'file'}
        asset.update(stored, **measured, script_hash=self.s['lock']['script_hash'], stale=False, review=None)
        self.s['assets'][data['id']] = asset
        self.invalidate(kind)
        return self.save('导入素材 ' + data['id'])

    def verify_asset(self, data):
        self.require_locked()
        a = self.s['assets'].get(data.get('id'))
        require(a and not a['stale'], '素材不存在或已失效')
        require(data.get('sha256') == a['sha256'] and data.get('reviewer') and data.get('evidence'), '素材审核缺少版本、审核人或依据')
        checks = {'audio': ('no_omission', 'no_repeat', 'no_truncation', 'voice_preserved'), 'image': ('identity', 'era', 'safe_motion', 'subtitle_space'), 'cover': ('consistency', 'readability', 'identity', 'rights'), 'music': ('rights', 'audibility'), 'sfx': ('rights', 'audibility')}[a['kind']]
        require(all(data.get('checks', {}).get(k) is True for k in checks), '素材审核检查未全部通过')
        a['review'] = data
        self.s['handoff'] = self.s['export'] = self.s['accepted'] = None
        return self.save('素材审核 ' + data['id'])

    def audio_ready(self):
        self.require_locked()
        require(self.s['audio_tasks'], '缺少网页配音任务')
        total = 0
        for task in self.s['audio_tasks']:
            a = self.s['assets'].get(task['id'])
            require(a and not a['stale'] and a['review'] and a.get('script_hash') == self.s['lock']['script_hash'], task['id'] + ' 音频缺失、过期或未试听验收')
            self.verify_file(a)
            total += a['seconds']
        expected = self.s['estimate']['audio_seconds']
        tolerance = self.s['estimate']['config'].get('audio_tolerance', 0.05)
        require(isinstance(tolerance, (int,float)) and 0 <= tolerance <= 1, '旁白偏差须在0至1范围')
        require(abs(total-expected) <= expected*tolerance, f'旁白实测 {total:.3f} 秒，偏离预期 {expected:.3f} 秒')
        return total

    def verify_file(self, a):
        path = inside(self.path, a['path'])
        require(path.is_file() and file_hash(path) == a['sha256'], '文件缺失或被改动：' + a['path'])

    def set_plan(self, data):
        self.require_locked()
        require(isinstance(data.get('shots'), list) and data['shots'], '需要镜头清单')
        require(data.get('responsible') and isinstance(data.get('transitions'), list), '需要负责人和转场清单')
        ids = set()
        for shot in data['shots']:
            require(re.fullmatch(r'K\d+', shot.get('id', '')) and shot['id'] not in ids, '镜头编号无效或重复')
            ids.add(shot['id'])
            require(shot.get('image') in self.s['assets'] and self.s['assets'][shot['image']]['kind'] == 'image', '镜头缺少源图片')
            require(shot.get('paragraphs') and set(shot['paragraphs']) <= {p['id'] for p in self.s['script']['paragraphs']}, '镜头段落映射无效')
            require(shot.get('motion') and shot.get('purpose') and shot.get('check_method'), '镜头缺少运动、目的或检查方法')
        self.s['plan'] = data
        self.s['handoff'] = self.s['export'] = self.s['accepted'] = None
        return self.save('更新镜头与转场计划')

    def coverage(self):
        end = self.audio_ready()
        plan = self.s['plan']
        require(plan, '缺少镜头计划')
        intervals = []
        for shot in plan['shots']:
            a = self.s['assets'][shot['image']]
            require(not a['stale'] and a['review'], '镜头引用未验收图片')
            self.verify_file(a)
            start, stop = shot.get('start'), shot.get('end')
            require(all(isinstance(x, (int,float)) and math.isfinite(x) for x in (start,stop)) and 0 <= start < stop <= end+0.05, '镜头实测时段缺失或越界')
            require(shot.get('time_basis') == 'AUDIO_VERIFIED' and shot.get('anchor_evidence'), '实测时段需要音频锚点依据')
            require(shot.get('start_crop') and shot.get('end_crop') and shot.get('safety_review'), '缺少裁切窗口和全过程安全复核')
            if shot['motion'] == 'static':
                e = shot.get('exception', {})
                require(all(e.get(k) for k in ('reason', 'alternatives', 'resume', 'reviewer')) and e.get('no_safe_motion') is True and e.get('narration_continues') is True and e.get('no_cut_point') is True and e.get('accepted') is True, '静止例外未经完整复审')
            intervals.append((start, stop, shot['id']))
        intervals.sort()
        cursor = 0
        previous = None
        for start, stop, kid in intervals:
            require(start <= cursor + 0.05, f'画面覆盖空档 {cursor:.3f}—{start:.3f}')
            if previous:
                matches = [t for t in plan['transitions'] if t.get('from') == previous and t.get('to') == kid]
                require(len(matches) == 1 and matches[0].get('semantic_reason') and matches[0].get('audio_continuity') and matches[0].get('ghosting_review'), '缺少相邻镜头语义、重影或声音连续性核验')
                t = matches[0]
                require(abs(float(t.get('overlap', 0)) - max(0, cursor-start)) <= 0.05, '转场重叠时长与镜头不符')
            cursor = max(cursor, stop)
            previous = kid
        require(abs(cursor-end) <= 0.05, '画面未覆盖完整旁白')
        return {'audio_seconds': end, 'covered_seconds': cursor}

    def production_hash(self):
        return digest({k:self.s[k] for k in ('lock', 'estimate', 'audio_tasks', 'assets', 'plan')})

    def document(self, stage):
        self.require_locked()
        require(stage in ('PLAN', 'TIMED', 'HANDOFF', 'EXECUTED', 'FINAL'), '文档阶段无效')
        if stage != 'PLAN':
            self.coverage()
        if stage == 'FINAL':
            require(self.s['accepted'], '尚无最终复审记录')
        if stage in ('EXECUTED', 'FINAL'):
            require(self.s['export'], '尚未登记实际导出')
        from .documents import generate
        version = len(self.s['documents']) + 1
        folder = self.path / f'05_AI剪辑交接包/剪辑文档/历史版本/v{version:03d}_{stage}_{uuid.uuid4().hex[:8]}'
        folder.mkdir(parents=True, exist_ok=False)
        self.s['editing_defaults'] = read(self.root / '00_项目配置/剪辑规则配置.json')
        files = generate(folder, self.s, stage, version)
        record = {'version': version, 'stage': stage, 'input_hash': self.production_hash(), 'files': [{'path': str(p.relative_to(self.path)), 'sha256': file_hash(p)} for p in files], 'time': now()}
        self.s['documents'].append(record)
        self.save('生成剪辑文档 ' + stage)
        return record

    def deliver(self):
        """Copy only production deliverables, never the application or working state."""
        settings = read(self.root / '00_项目配置/工作台配置.json')
        require(settings.get('output_dir'), '尚未配置生产资料输出目录；使用 init --output-dir 设置')
        output = Path(settings['output_dir']).expanduser().resolve()
        require(not output.is_relative_to(self.root) and not self.root.is_relative_to(output), '输出目录与运行目录不可嵌套')
        files = {}
        if self.s['lock']:
            self.require_locked()
            path = self.path / '02_故事文稿/口播定稿.txt'
            require(path.read_text(encoding='utf-8') == self.s['script']['text'], '定稿文件与锁稿文字不同')
            files[str(path.relative_to(self.path))] = file_hash(path)
        for asset in self.s['assets'].values():
            if not asset['stale']:
                self.verify_file(asset)
                files[asset['path']] = asset['sha256']
        if self.s['export']:
            for asset in (self.s['export']['video'], self.s['export'].get('project')):
                if asset:
                    self.verify_file(asset)
                    files[asset['path']] = asset['sha256']
        if self.s['audio_tasks']:
            folder = self.path / f'04_素材/音频/网页文本包/{digest(self.s["audio_tasks"])[:12]}'
            for path in folder.glob('*'):
                if path.is_file():
                    files[str(path.relative_to(self.path))] = file_hash(path)
        if self.s['documents']:
            latest = self.s['documents'][-1]
            if latest['input_hash'] == self.production_hash():
                for artifact in latest['files']:
                    self.verify_file(artifact)
                    files[artifact['path']] = artifact['sha256']
        require(files, '本集尚无可交付的生产资料')
        parent = inside(output, self.s['episode'])
        parent.mkdir(parents=True, exist_ok=True)
        label = f'r{self.s["revision"]:05d}_{uuid.uuid4().hex[:8]}'
        staging = parent / ('.pending-' + label)
        target = parent / label
        staging.mkdir()
        try:
            for relative, expected in files.items():
                source = inside(self.path, relative)
                destination = inside(staging, relative)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                require(file_hash(destination) == expected, '生产资料复制校验失败')
            write(staging / '生产资料清单.json', {'episode': self.s['episode'], 'revision': self.s['revision'], 'status': self.s['status'], 'time': now(), 'files': files, 'note': '制作中资料不代表成片已验收；以本版状态为准。'})
            staging.rename(target)
        except Exception:
            shutil.rmtree(staging)
            raise
        return {'directory': str(target), 'files': len(files), 'status': self.s['status']}

    def handoff(self):
        self.coverage()
        caps_path = self.root / '00_项目配置/已核验工具.json'
        require(caps_path.exists(), '剪辑工具尚未选择并完成能力核验')
        caps = read(caps_path)
        validate_caps(caps)
        covers = [a for a in self.s['assets'].values() if a['kind']=='cover' and not a['stale'] and a['review']]
        require(covers, '缺少已独立审核封面')
        for a in self.s['assets'].values():
            if not a['stale']:
                self.verify_file(a)
        doc = self.document('HANDOFF')
        self.s['handoff'] = {'input_hash': self.production_hash(), 'document': doc['version'], 'tool': caps, 'time': now()}
        self.s['status'] = 'WAITING_AI_EDIT'
        self.save('冻结通用剪辑交接版')
        # Copy complete episode with relative paths; no custom editor format is claimed.
        folder = self.root / '交接归档'
        folder.mkdir(exist_ok=True)
        base = folder / f'{self.s["episode"]}_r{self.s["revision"]:05d}'
        archive = shutil.make_archive(str(base), 'zip', self.path)
        return {'archive': archive, 'state': self.s['status'], 'format': '普通文件包，需人工导入；不是剪辑软件工程'}

    def register_export(self, data):
        require(self.s['handoff'] and self.s['handoff']['input_hash'] == self.production_hash(), '交接版本缺失或已失效')
        frozen = next(d for d in self.s['documents'] if d['version'] == self.s['handoff']['document'])
        for artifact in frozen['files']:
            self.verify_file(artifact)
        require(data.get('settings') and data.get('executed_by'), '需回填实际工具设置与执行人')
        require(data.get('project_file') or data.get('project_url'), '需归档可编辑工程或云工程链接')
        measured = duration(data['file'], video=True)
        video = self.copy_asset(data['file'], '导出原件')
        project = self.copy_asset(data['project_file'], '工程原件') if data.get('project_file') else None
        self.s['export'] = {**{k:v for k,v in data.items() if k not in ('file','project_file')}, 'video': video, 'project': project, 'seconds': measured, 'input_hash': self.production_hash()}
        self.s['accepted'] = None
        self.s['status'] = 'PREVIEW_REVIEW'
        self.save('登记外部导出，待复审')
        return self.document('EXECUTED')

    def accept(self, data):
        self.coverage()
        export = self.s['export']
        require(export and export['input_hash'] == self.production_hash(), '缺少当前版本成片')
        self.verify_file(export['video'])
        if export.get('project'):
            self.verify_file(export['project'])
        require(data.get('video_hash') == export['video']['sha256'] and data.get('reviewer') and data.get('evidence'), '成片复审版本或记录不全')
        require(all(data.get('checks', {}).get(k) is True for k in FINAL_CHECKS), '成片复审未全部完成')
        for artifact in self.s['documents'][-1]['files']:
            self.verify_file(artifact)
        require(self.s['range'][0] <= export['seconds'] <= self.s['range'][1], '成片实测时长不达标')
        require(data.get('execution_matches_document') is True, '实际执行设置与文档尚未核对')
        self.s['accepted'] = {**data, 'time': now()}
        self.document('FINAL')
        self.s['status'] = 'FINAL_ACCEPTED'
        return self.save('成片复审及文档定版')


def validate_caps(data):
    require(data.get('name') and data.get('version') and data.get('tester'), '工具名称、版本和测试人不可缺少')
    for key in CAPS:
        item = data.get('checks', {}).get(key, {})
        require(item.get('passed') is True and item.get('evidence'), '工具能力尚未实测：' + key)
