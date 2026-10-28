"""Candidate selection and user-authored creative briefs, separate from evidence."""
import copy
import re
from .core import require, read, write, now, digest, exclusive, new_episode
from .story_history import profile, check, ensure_distinct


def batch_path(root, batch_id):
    require(isinstance(batch_id, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', batch_id), '候选批次编号仅允许字母、数字、下划线、短横线')
    return root / '01_选题库/候选批次' / (batch_id + '.json')


def save_options(root, data):
    path = batch_path(root, data.get('id'))
    options = data.get('options')
    require(isinstance(options, list) and 2 <= len(options) <= 10, '请提供2—10个候选选题')
    ids = set()
    for option in options:
        require(isinstance(option, dict), '选题必须是对象')
        for key in ('id', 'title', 'summary', 'angle'):
            require(isinstance(option.get(key), str) and option[key].strip(), '选题缺少 ' + key)
        require(option['id'] not in ids, '候选编号重复')
        ids.add(option['id'])
        profile(option.get('story'))
    with exclusive(root):
        require(not path.exists(), '批次已存在；请用新编号保存修订，避免覆盖已选内容')
        prior, checks = [], {}
        for option in options:
            result = check(root, option['story'], extra_records=prior)
            ensure_distinct(result)
            checks[option['id']] = result
            prior.append({'id': option['id'], 'title': option['title'], 'story': option['story'], 'status': 'SAME_BATCH'})
        write(path, {**data, 'created_at': now(), 'status': 'AWAITING_USER_SELECTION', 'storyline_checks': checks})
    return {'saved': str(path), 'batch': data['id'], 'options': options}


def select(root, batch_id, candidate_id, idea='', minimum=1800, maximum=1860):
    data = read(batch_path(root, batch_id))
    matches = [o for o in data['options'] if o['id'] == candidate_id]
    require(len(matches) == 1, '候选编号不存在')
    profile(matches[0].get('story'))
    require(isinstance(idea, str), '个人想法必须是文本')
    brief = {'batch_id': batch_id, 'batch_hash': digest(data), 'selected': copy.deepcopy(matches[0]),
             'ideas': [{'text': idea.strip(), 'created_at': now()}] if idea.strip() else [],
             'instruction': '选题角度与用户想法是创作要求，不是史实证据；事实主张须单独核查。'}
    return new_episode(root, matches[0]['title'], minimum, maximum, brief=brief)


def add_idea(episode, text, reason=None):
    require(isinstance(text, str) and text.strip(), '个人想法不能为空')
    episode.editable(reason)
    brief = episode.s.setdefault('creative_brief', {'selected': {'title': episode.s['title']}, 'ideas': [],
        'instruction': '用户想法是创作要求，不是史实证据。'})
    brief['ideas'].append({'text': text.strip(), 'created_at': now()})
    episode.invalidate('evidence')
    episode.s['stage_reviews'] = {}
    return episode.save('追加用户创作想法；重开理由：' + (reason or '未锁稿'))
