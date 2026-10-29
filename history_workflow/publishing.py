"""Versioned local publishing copy; never posts or promises platform reach."""
import copy
import re
import shutil
import uuid
from .core import WorkflowError, digest, file_hash, inside, now, read, require, write

PLATFORMS = {
    'DOUYIN':'抖音', 'BILIBILI':'B站', 'XIGUA':'西瓜视频', 'TOUTIAO':'今日头条',
    'WEIXIN':'微信视频号', 'KUAISHOU':'快手', 'YOUTUBE':'YouTube',
    'XIAOHONGSHU':'小红书', 'ALIPAY':'支付宝', 'PINDUODUO':'拼多多',
    'BAIJIAHAO':'百家号',  # Legacy opt-in, no longer in the default platform list.
}
DEFAULT_PLATFORM_IDS = [p for p in PLATFORMS if p != 'BAIJIAHAO']
DEFAULTS = {
    'version': 2, 'platforms': DEFAULT_PLATFORM_IDS,
    'cover_preferences': {p:['LANDSCAPE_16_9','LANDSCAPE_4_3','PORTRAIT_3_4','PORTRAIT_9_16'] for p in DEFAULT_PLATFORM_IDS},
    'title_policy': '发布标题与视频完整标题一致；可选副标题单列。平台超长时提示，不自动截断。',
    'copy_policy': '从锁稿提炼，不新增史实、不虚构原因、不承诺流量。',
    'delivery_policy': '封面按比例复用，平台页复核适用性；仅本地发布包，不执行发布。',
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


def inputs(episode, content, settings, analysis=None, covers=None):
    return digest({'script': episode.s['script'], 'video_title': video_title(episode.s),
                   'publication':episode.s.get('publication'), 'copy': content, 'settings': settings, 'tag_analysis':analysis, 'covers':covers,
                   'cover_assets':{k:{f:a.get(f) for f in ('sha256','path','publication_title','main_title','subtitle')} for k,a in episode.s.get('assets',{}).items() if a.get('kind')=='cover'}})


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
    from .tags import config as tag_config, library, match
    from .covers import delivery_status
    analysis = match(episode.s, tag_config(episode.root), library(episode.root), settings['platforms'], content['tags'])
    covers = delivery_status(episode.s)
    rules_path=episode.root/'00_项目配置/平台推荐规则索引.json'
    rules=read(rules_path) if rules_path.exists() else {'platforms':{}}
    analysis['recommendation_rules']=rules
    from .monetization import snapshot as monetization_snapshot
    analysis['monetization']=monetization_snapshot(episode.root, settings['platforms'])
    article={'status':'NOT_PREPARED'}
    if episode.s.get('toutiao_article_packages'):
        from .articles import check_article
        try:
            article=check_article(episode)
        except WorkflowError as exc:
            article={'status':'STALE_NEEDS_ADAPTATION','reason':str(exc)}
    analysis['toutiao_article']=article
    complete = all(content[k] for k in ('body', 'short_body', 'content_note'))
    return {'schema': 2, 'status': 'COPY_READY_FOR_PLATFORM_REVIEW' if complete else 'DRAFT_NEEDS_COPY',
            'title': title, 'copy': content, 'settings': settings,
            'input_hash': inputs(episode, content, settings, analysis, covers),
            'tag_analysis': analysis, 'covers': covers,
            'platforms': {p: {'title': title, 'subtitle': content['subtitle'],
                             'description': content['short_body'] if p in ('DOUYIN', 'KUAISHOU', 'XIAOHONGSHU') else content['body'],
                             'tags': analysis['platforms'][p]['tags'],
                             'metadata_tags': analysis['platforms'][p]['tags'] if p == 'YOUTUBE' else [],
                             'cover_options': settings.get('cover_preferences',{}).get(p, list(covers['targets'])),
                             'pinned_comment': content['pinned_comment'],
                             'content_note': content['content_note']} for p in settings['platforms']},
            'notice': '文案就绪不代表成片验收通过、已发布或已获收益资格；发布前复核本账号页面。'}


def save_package(episode, data=None):
    bundle = build(episode, data)
    records = episode.s.get('publication_packages', [])
    version = len(records) + 1
    folder = episode.path / f'08_发布包/历史版本/v{version:03d}_{uuid.uuid4().hex[:8]}'
    write(folder / '发布文案.json', bundle)
    for target, spec in bundle['covers']['targets'].items():
        for aid in reversed(spec['asset_ids']):
            asset=episode.s['assets'][aid]
            publication=episode.s.get('publication') or {}
            # Legacy covers were bound to the separately reviewed main/subtitle.
            exact_title=asset.get('publication_title') == bundle['title']
            exact_parts=bool(publication.get('main_title')) and asset.get('main_title') == publication['main_title'] and asset.get('subtitle','') == publication.get('subtitle','')
            if not (exact_title or exact_parts):
                continue
            source=inside(episode.path,asset['path'])
            require(source.is_file() and file_hash(source)==asset['sha256'], '封面文件缺失或被修改')
            out=folder/'封面'/spec['filename']; out.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,out)
            break
    article=bundle['tag_analysis']['toutiao_article']
    if article.get('files'):
        for item in article['files']:
            source=inside(episode.path,item['path'])
            target=folder/'今日头条文字版'/source.name;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,target)
    from .covers import DEFAULTS as COVER_DEFAULTS
    cover_labels={k:v['label'] for k,v in {**COVER_DEFAULTS['targets'],**COVER_DEFAULTS['optional_targets'],**(episode.s.get('cover_plan') or {}).get('targets',{})}.items()}
    lines=['# 本集发布资料', '', '完整视频标题：'+bundle['title'], '',
           '封面主标题：'+(episode.s.get('publication') or {}).get('main_title', bundle['title']), '',
           '封面副标题：'+(episode.s.get('publication') or {}).get('subtitle',''), '',
           '可选简介吸引句：'+bundle['copy']['subtitle'], '',
           '其他可选吸引句：'+'；'.join(bundle['copy']['subtitle_options']), '',
           '封面按比例通用；下列比例供选择，不代表已核定所有平台上传规格。', '',
           '| 封面 | 本包状态 |', '|---|---|']
    for spec in bundle['covers']['targets'].values():
        lines.append('| '+spec['label']+' | '+('已附图' if (folder/'封面'/spec['filename']).exists() else '待制作/核验')+' |')
    for key,spec in COVER_DEFAULTS['optional_targets'].items():
        if key not in bundle['covers']['targets']: lines.append('| '+spec['label']+' | 按需规格，本集未启用/未附图 |')
    lines += ['', '## 平台文案与标签', '']
    for platform, content in bundle['platforms'].items():
        report=bundle['tag_analysis']['platforms'][platform]
        rule=bundle['tag_analysis']['recommendation_rules'].get('platforms',{}).get(platform,{'summary':'尚未核实官方规则','sources':[]})
        lines += ['### '+PLATFORMS[platform], '', '标题：'+content['title'], '',
                  '副标题文案（可选，简介首行）：'+content['subtitle'], '', '正文：'+content['description'], '',
                  '话题标签：'+' '.join('#'+t for t in content['tags']), '',
                  '封面选择：'+'、'.join(cover_labels.get(k,k) for k in content['cover_options'])+'（按实际发布页裁切选择）', '',
                  '内容说明：'+content['content_note'], '', '置顶评论：'+content['pinned_comment'], '',
                  '热点检索：'+report['retrieval_status']+'；'+report['retrieval_note'],
                  '快照新鲜度：'+('7日内；发布前仍需复查' if report['fresh'] else '缺失或过期，不能当作当前热点'), '',
                  '公开推荐规则：'+rule['summary'],
                  '规则来源：'+'；'.join(rule.get('sources',[])), '']
        earnings=bundle['tag_analysis']['monetization']
        account=earnings['platforms'][platform]
        plan=account['public_plan']
        lines += ['收益计划：'+plan.get('program','尚未核实适用计划'), '',
                  '公开资料核对日期：'+str(earnings['checked_at'] or '未核对')+'；'+('7日内检索，仍需核对账号页' if earnings['fresh'] else '缺失或超过7日，发布前重新核对'), '',
                  '证据范围：'+plan.get('evidence_status','NOT_RESEARCHED'), '',
                  '参与判断：'+plan.get('summary','需检索官方现行规则'), '',
                  '本账号资格：'+account['account_status']+'；'+account['account_note'], '',
                  '查看入口：'+plan.get('entry','待核验'), '', '参与条件与待办：', '']
        for item in plan.get('conditions',[]): lines.append('- '+item)
        for item in plan.get('next_actions',[]): lines.append('- '+item)
        for item in plan.get('sources',[]): lines.append('- 收益资料：['+item['title']+']('+item['url']+')')
        lines += ['', '标签依据：', '']
        if platform == 'YOUTUBE': lines += ['', 'YouTube普通tags（无#，单独填元数据栏）：'+', '.join(content['metadata_tags']), '']
        for item in report['selected']: lines.append('- '+item['tag']+'：'+item['reason'])
        for item in report['hot_matches']: lines.append('- 可匹配热点：'+item['tag']+'；'+item['reason']+'；'+item['url'])
        for item in report['rejected']: lines.append('- 未采用线索：'+item['tag']+'；'+item['reason']+'；'+item['url'])
        lines.append('')
    article_label={'NOT_PREPARED':'尚未制作', 'STALE_NEEDS_ADAPTATION':'需按当前稿件重新核对', 'READY_FOR_MANUAL_UPLOAD':'文章已就绪，视频已通过最终验收', 'ARTICLE_READY_VIDEO_REVIEW_PENDING':'文章已就绪，视频最终复审仍待完成'}.get(article['status'],article['status'])
    lines += ['## 今日头条文字版专项内容', '', '状态：'+article_label,
              '完整文章、排版HTML及结构化数据：见本包的今日头条文字版文件夹。' if article.get('files') else '文字版尚未就绪；运行article-packet读取改写依据，再用article-package导入审核后的文章。',
              '手动发布：打开HTML，分别复制标题和排版正文；上传后复核段落、标题、内容说明及封面。当前未执行上传。', '']
    lines += ['## 发布前检查', '', bundle['notice'], bundle['tag_analysis']['notice']]
    write(folder / '发布资料汇总.md', '\n'.join(lines)+'\n')
    record = {'version': version, 'time': now(), 'input_hash': bundle['input_hash'],
              'status': bundle['status'], 'directory': str(folder.relative_to(episode.path)),
              'files': [{'path': str(f.relative_to(episode.path)), 'sha256': file_hash(f)}
                        for f in sorted(folder.rglob('*')) if f.is_file()]}
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
