"""Evidence-backed local topic snapshots and explainable content matching."""
import copy
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse
from .core import digest, now, read, require, write

OFFICIAL_HOSTS = {'DOUYIN':('douyin.com',), 'BILIBILI':('bilibili.com','hdslb.com'),
    'XIGUA':('ixigua.com',), 'TOUTIAO':('toutiao.com',), 'WEIXIN':('weixin.qq.com','qq.com'),
    'KUAISHOU':('kuaishou.com',), 'YOUTUBE':('youtube.com','google.com'),
    'XIAOHONGSHU':('xiaohongshu.com',), 'ALIPAY':('alipay.com',),
    'PINDUODUO':('pinduoduo.com','yangkeduo.com','pddpic.com')}

DEFAULTS = {
    'version': 1, 'refresh_days': 7, 'maximum_tags': 6,
    'account_genre': '名人相关的历史细节说书',
    'fixed_tags': ['历史故事'],
    'content_rules': [
        {'tag':'明朝历史', 'keywords':['张居正','万历','曾省吾','王篆']},
        {'tag':'张居正', 'keywords':['张居正']}, {'tag':'万历', 'keywords':['万历']},
        {'tag':'曾省吾', 'keywords':['曾省吾']}, {'tag':'王篆', 'keywords':['王篆']}],
    'policy':'先内容相关，再考察热度；固定标签不是热榜。评分是项目筛选规则，不是平台算法或流量预测。',
}


def config(root):
    p = root/'00_项目配置/视频标签配置.json'
    c = read(p) if p.exists() else copy.deepcopy(DEFAULTS)
    require(isinstance(c.get('maximum_tags'), int) and 1 <= c['maximum_tags'] <= 20, '标签数量须为1—20的项目自定值')
    require(isinstance(c.get('refresh_days'), int) and c['refresh_days'] > 0, '更新周期须为正整数')
    for rule in c.get('content_rules', []):
        valid_tag(rule['tag']); require(isinstance(rule['keywords'], list) and rule['keywords'] and all(isinstance(k,str) and len(k.strip()) >= 2 for k in rule['keywords']), '内容匹配词至少2字')
    for tag in c.get('fixed_tags', []): valid_tag(tag)
    return c


def valid_tag(tag):
    require(isinstance(tag,str) and tag.strip() == tag and tag and not any(c.isspace() or c == '#' for c in tag), '标签须为不带#和空白的名称')


def timestamp(value):
    require(isinstance(value,str), '时间须为ISO字符串')
    try:
        d = datetime.fromisoformat(value.replace('Z','+00:00'))
        require(d.tzinfo is not None, '时间必须带时区')
        return d
    except ValueError:
        require(False, '时间格式无效')


def validate_snapshot(data, clock=None):
    from .publishing import DEFAULT_PLATFORM_IDS
    clock = clock or datetime.now(timezone.utc)
    require(isinstance(data,dict) and data.get('schema') == 1, '热点快照格式无效')
    observed = timestamp(data.get('retrieved_at'))
    require(observed <= clock, '检索时间不能在未来')
    require(set(data.get('platforms',{})) == set(DEFAULT_PLATFORM_IDS), '快照须逐项覆盖10个平台，失败也须记录')
    for platform, record in data['platforms'].items():
        require(record.get('status') in ('OBSERVED','PARTIAL','UNAVAILABLE','NOT_FOUND'), '检索状态无效')
        require(record.get('query') and record.get('note'), '缺少检索词或结果说明')
        require(isinstance(record.get('items'),list), '热点条目须为列表')
        for item in record['items']:
            valid_tag(item.get('tag'))
            require(item.get('kind') in ('HASHTAG','SEARCH_TREND','ACTIVITY','CONTENT_SAMPLE'), '须区分话题、热搜、活动和样本')
            require(item.get('source_kind') in ('OFFICIAL','THIRD_PARTY'), '缺少来源类别')
            require(urlparse(item.get('url','')).scheme in ('https','http') and urlparse(item['url']).netloc, '来源链接无效')
            if item['source_kind'] == 'OFFICIAL':
                host=urlparse(item['url']).hostname or ''
                require(any(host==h or host.endswith('.'+h) for h in OFFICIAL_HOSTS[platform]), '官方来源域名与平台不符')
            require(item.get('evidence'), '缺少观测证据')
            if item['kind'] == 'HASHTAG':
                require(timestamp(item.get('trend_at')) <= observed, '话题须有可核实的榜单/活动时间，不能以访问时间代替')
            if item.get('valid_until'):
                timestamp(item['valid_until'])
            require(timestamp(item.get('observed_at')) <= clock, '热点观测时间不能在未来')
            require(timestamp(item['observed_at']) <= observed, '热点观测不能晚于检索结束')
            require(isinstance(item.get('keywords'),list) and all(isinstance(k,str) and len(k.strip()) >= 2 for k in item['keywords']), '热点匹配词至少2字')
    return data


def import_snapshot(root, data):
    validate_snapshot(data)
    folder = root/'02_公共素材库/平台热点库'
    ident = uuid.uuid4().hex[:12]
    write(folder/f'历史快照/{data["retrieved_at"][:10]}_{ident}.json', data)
    write(folder/'最新快照.json', data)
    return {'saved':str(folder/'最新快照.json'), 'snapshot_hash':digest(data)}


def library(root):
    p = root/'02_公共素材库/平台热点库/最新快照.json'
    return validate_snapshot(read(p)) if p.exists() else None


def match(state, settings, snapshot, platforms, content_tags=(), clock=None):
    clock = clock or datetime.now(timezone.utc)
    script = state.get('script',{}).get('text','')
    title = (state.get('publication') or {}).get('title','')
    corpus = title + '\n' + script
    stable = [{'tag':t,'kind':'FIXED','reason':'账号长期内容定位：'+settings['account_genre']} for t in settings.get('fixed_tags',[])]
    candidates = list(settings.get('content_rules',[])) + [{'tag':t,'keywords':[t]} for t in content_tags if len(t)>=2]
    for item in candidates:
        hit = [k for k in item['keywords'] if k in corpus]
        if hit:
            stable.append({'tag':item['tag'], 'kind':'CONTENT', 'reason':'口播稿/标题命中：'+ '、'.join(hit), 'matched_keywords':hit})
    results = {}
    for p in platforms:
        record = (snapshot or {}).get('platforms',{}).get(p,{})
        accepted, rejected = [], []
        for item in record.get('items',[]):
            age = (clock-min(timestamp(item['observed_at']), timestamp(item.get('trend_at',item['observed_at'])))).total_seconds()/86400
            hit = [k for k in item['keywords'] if k in corpus]
            # Hashtags must be observed as such. News titles and activity names cannot silently become tags.
            reasons=[]
            if age > settings['refresh_days']: reasons.append('观测已过期，发布前需重查')
            if item.get('valid_until') and clock > timestamp(item['valid_until']): reasons.append('话题/活动有效期已结束')
            if not hit: reasons.append('本集正文没有相关匹配词')
            if item['source_kind'] != 'OFFICIAL': reasons.append('第三方线索，需在平台内核实')
            if item['kind'] != 'HASHTAG': reasons.append('不是已验证的平台话题标签')
            entry={**item,'matched_keywords':hit,'reason':'；'.join(reasons) if reasons else '官方话题且本集内容直接命中；上传前复查活动条件'}
            (rejected if reasons else accepted).append(entry)
        unique={}
        # Content identity comes before hot candidates; no unrelated hot tags fill spare slots.
        hot=[{**i,'kind':'HOT_MATCH'} for i in accepted]
        reserve=min(2,len(hot),max(0,settings['maximum_tags']-1))
        for item in stable[:settings['maximum_tags']-reserve] + hot + stable: unique.setdefault(item['tag'],item)
        selected=list(unique.values())[:settings['maximum_tags']]
        results[p]={'tags':[i['tag'] for i in selected], 'selected':selected, 'hot_matches':accepted,'rejected':rejected,
                    'retrieval_status':record.get('status','NO_SNAPSHOT'), 'retrieval_note':record.get('note','尚无热点快照'),
                    'fresh':bool(snapshot) and (clock-timestamp(snapshot['retrieved_at'])).total_seconds() <= settings['refresh_days']*86400}
    return {'basis':'LOCKED_SCRIPT_AND_ACCOUNT_PROFILE', 'script_hash':digest(state.get('script',{})),
            'snapshot_hash':digest(snapshot), 'snapshot_at':(snapshot or {}).get('retrieved_at'),
            'settings':settings, 'platforms':results, 'notice':'无匹配可以只用内容标签；热榜不等于标签，标签不保证推荐或播放量。'}
