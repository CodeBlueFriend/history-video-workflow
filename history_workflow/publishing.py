"""Versioned local publishing copy; never posts or promises platform reach."""
import copy
import re
import uuid
from .core import digest, file_hash, inside, now, read, require, write

PLATFORMS = {
    'BILIBILI': 'B站', 'DOUYIN': '抖音', 'WEIXIN': '视频号',
    'XIGUA': '西瓜视频与今日头条', 'KUAISHOU': '快手', 'YOUTUBE': 'YouTube',
    'XIAOHONGSHU': '小红书', 'BAIJIAHAO': '百家号',
}
DEFAULTS = {
    'version': 1, 'platforms': list(PLATFORMS),
    'title_policy': '发布标题与本集视频完整标题逐字一致，副标题文案单列；平台超长时提示人工处理，不自动截断。',
    'copy_policy': '从锁稿提炼背景、人物关系与悬念，不新增事实、不把待核指控坐实、不虚构原因或承诺流量。',
    'delivery_policy': '仅生成本地发布包，不登录或发布；平台字数、上传资格、原创及AI标识按实际页面复核。',
}


def config(root):
    path = root / '00_项目配置/发布文案配置.json'
    result = read(path) if path.exists() else copy.deepcopy(DEFAULTS)
    require(isinstance(result.get('platforms'), list) and result['platforms'], '缺少发布平台')
    require(len(set(result['platforms'])) == len(result['platforms']) and
            all(p in PLATFORMS for p in result['platforms']), '发布平台未知或重复')
    return result


def video_title(state):
    title = (state.get('publication') or {}).get('title') or (state.get('script') or {}).get('title') or state['title']
    require(isinstance(title, str) and title.strip() and '\n' not in title, '缺少单行视频完整标题')
    return title


def normalize_copy(data, title):
    require(isinstance(data, dict), '发布文案须为JSON对象')
    allowed = {'title', 'subtitle', 'subtitle_options', 'body', 'short_body', 'tags', 'pinned_comment', 'content_note'}
    require(set(data) <= allowed, '发布文案含未知字段')
    require(data.get('title', title) == title, '发布标题必须与视频完整标题逐字一致；吸引句请填subtitle')
    result = {'title': title}
    for key in ('subtitle', 'body', 'short_body', 'pinned_comment', 'content_note'):
        value = data.get(key, '')
        require(isinstance(value, str), key + '须为文本')
        result[key] = value.strip()
    for key in ('tags', 'subtitle_options'):
        value = data.get(key, [])
        require(isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value), key + '须为非空文本列表')
        result[key] = list(dict.fromkeys(v.strip() for v in value))
    require(all(not re.search(r'[\s#]', t) for t in result['tags']), '话题请填写不含空白和#的名称')
    return result


def inputs(episode, content, settings):
    return digest({'script': episode.s['script'], 'video_title': video_title(episode.s),
                   'copy': content, 'settings': settings})


def build(episode, data=None):
    episode.require_locked()
    title = video_title(episode.s)
    if data is None:
        bound = episode.s.get('publication_copy_script_hash') == digest(episode.s['script'])
        data = copy.deepcopy(episode.s.get('publication_copy') or {}) if bound else {}
        # A revised video title is authoritative; keep the old version in history.
        data['title'] = title
    content = normalize_copy(data, title)
    settings = config(episode.root)
    complete = all(content[k] for k in ('body', 'short_body', 'content_note'))
    return {'schema': 1, 'status': 'COPY_READY_FOR_PLATFORM_REVIEW' if complete else 'DRAFT_NEEDS_COPY',
            'title': title, 'copy': content, 'settings': settings,
            'input_hash': inputs(episode, content, settings),
            'platforms': {p: {'title': title, 'subtitle': content['subtitle'],
                             'description': content['short_body'] if p in ('DOUYIN', 'KUAISHOU', 'XIAOHONGSHU') else content['body'],
                             'tags': content['tags'], 'pinned_comment': content['pinned_comment'],
                             'content_note': content['content_note']} for p in settings['platforms']},
            'notice': '文案就绪不代表成片验收通过、已发布或已获收益资格；发布前复核本账号页面。'}


def save_package(episode, data=None):
    bundle = build(episode, data)
    records = episode.s.get('publication_packages', [])
    version = len(records) + 1
    folder = episode.path / f'08_发布包/历史版本/v{version:03d}_{uuid.uuid4().hex[:8]}'
    write(folder / '发布文案.json', bundle)
    for platform, content in bundle['platforms'].items():
        text = ('标题：' + content['title'] + '\n\n副标题文案（可选，放简介首行）：\n' + content['subtitle'] +
                '\n\n正文：\n' + content['description'] + '\n\n话题：\n' +
                ' '.join('#' + tag for tag in content['tags']) + '\n\n内容说明：\n' +
                content['content_note'] + '\n\n置顶评论（可选）：\n' + content['pinned_comment'] + '\n')
        write(folder / f'{platform}_发布文案.txt', text)
    record = {'version': version, 'time': now(), 'input_hash': bundle['input_hash'],
              'status': bundle['status'], 'directory': str(folder.relative_to(episode.path)),
              'files': [{'path': str(f.relative_to(episode.path)), 'sha256': file_hash(f)}
                        for f in sorted(folder.iterdir()) if f.is_file()]}
    episode.s['publication_copy'] = bundle['copy']
    episode.s['publication_copy_script_hash'] = digest(episode.s['script'])
    episode.s.setdefault('publication_packages', []).append(record)
    episode.save('生成本地发布文案包；标题与视频一致，未执行发布')
    return record


def check_package(episode):
    episode.require_locked()
    records = episode.s.get('publication_packages', [])
    require(records, '缺少发布文案包；先运行publication-package')
    latest = records[-1]
    current = build(episode)
    require(latest['input_hash'] == current['input_hash'], '发布文案包已过期：正文、标题、文案或配置变化，请重新生成')
    for item in latest['files']:
        path = inside(episode.path, item['path'])
        require(path.is_file() and file_hash(path) == item['sha256'], '发布包文件缺失或被修改，请重新生成')
    return latest
