"""Story-led visual resource planning, snapshotted per episode."""
import copy
import math
from .core import read, require

DEFAULTS = {
    'version':1,
    'duration_seconds':{'minimum':900,'maximum':3600},
    'images':{'per_video_minute':1.5,'minimum':12,'enforce_from_seconds':300,
              'required_roles':['SETTING','KEY_EVENT','TURNING_POINT','OUTCOME'],
              'role_labels':{'SETTING':'开场环境与人物关系','KEY_EVENT':'核心事件','TURNING_POINT':'关键转折','OUTCOME':'结局与后果'},
              'max_continuous_image_seconds':120},
    'policy':'按故事语义规划图片；数量是资源基准，不是定时切图指令。关键情节由创作者逐段判断，实际成图及镜头映射须核验。少图或长图需记录原因及复核，不能用拆运动段冒充新图片。',
}


def config(root):
    path=root/'00_项目配置/制作规划配置.json'
    c=read(path) if path.exists() else copy.deepcopy(DEFAULTS)
    d=c['duration_seconds']; i=c['images']
    require(0 < d['minimum'] <= d['maximum'] <= 3600, '正式视频默认时长须在60分钟以内')
    require(all(isinstance(i[k],(int,float)) and not isinstance(i[k],bool) and math.isfinite(i[k]) and i[k]>0 for k in ('per_video_minute','minimum','enforce_from_seconds','max_continuous_image_seconds')), '图片规划参数须为有限正数')
    require(i['required_roles'] and all(r in i['role_labels'] for r in i['required_roles']), '关键画面角色配置无效')
    return c


def seconds(state):
    measured=(state.get('estimate') or {}).get('video_seconds')
    if measured:return measured
    if (state.get('script') or {}).get('text'):
        from .budget import preflight, DEFAULTS as BUDGET
        return preflight(state,BUDGET)['estimated_video_seconds']
    return state.get('range',[900,3600])[0]


def recommended_count(duration,settings):
    return max(math.ceil(settings['minimum']),math.ceil(duration/60*settings['per_video_minute']))


def report(state,plan=None):
    policy=state.get('visual_policy')
    if not policy:return {'status':'LEGACY_NOT_ADOPTED','note':'旧集未采用新规划，不改写原有工程；新集自动快照。'}
    duration=seconds(state);settings=policy['images'];plan=plan or state.get('plan') or {}
    return {'status':'PLANNING','estimated_seconds':duration,
            'recommended_body_images':recommended_count(duration,settings),
            'planned_distinct_images':len({s.get('image') for s in plan.get('shots',[]) if s.get('image')}),
            'required_roles':{r:settings['role_labels'][r] for r in settings['required_roles']},
            'critical_scenes':plan.get('critical_scenes',[]),'policy':policy,
            'note':'按故事从锁稿逐段列关键画面，不能以预算或关键词判断冒充语义核验。'}


def reviewed_exception(value):
    return isinstance(value,dict) and value.get('reviewer') and value.get('reason') and value.get('evidence') and value.get('accepted') is True


def check(state,plan,timed=False):
    policy=state.get('visual_policy')
    if not policy or state.get('production_kind')=='SAMPLE':return
    duration=seconds(state);settings=policy['images']
    if duration < settings['enforce_from_seconds']:return
    scenes=plan.get('critical_scenes')
    require(isinstance(scenes,list) and scenes,'缺少按锁稿列出的关键画面清单')
    require(set(settings['required_roles']) <= {s.get('role') for s in scenes},'关键画面须覆盖开场、核心事件、转折及结局')
    ids=set();images=set();paragraphs={p['id'] for p in state['script']['paragraphs']}
    for scene in scenes:
        require(scene.get('id') and scene['id'] not in ids,'关键画面编号缺失或重复');ids.add(scene['id'])
        require(scene.get('description') and scene.get('reason') and scene.get('paragraphs') and set(scene['paragraphs']) <= paragraphs,'关键画面缺少内容、必要性或有效段落')
        image=scene.get('image');asset=state.get('assets',{}).get(image,{})
        require(asset.get('kind')=='image' and image not in images,'每项关键画面须绑定独立源图片，不能共用一张通用背景');images.add(image)
        require(set(scene['paragraphs']) <= set(asset.get('paragraphs',[])), '关键图片与情节段落不对应')
        shots=[s for s in plan.get('shots',[]) if s.get('image')==image]
        covered={p for s in shots for p in s.get('paragraphs',[])}
        require(set(scene['paragraphs']) <= covered, '关键图片未实际用于对应段落镜头')
    planned=len({s['image'] for s in plan['shots']})
    require(planned >= recommended_count(duration,settings) or reviewed_exception(plan.get('image_density_exception')), '正文图片不足资源规划基准，须补图或记录实际少图复核')
    if not timed:return
    longest=0;active=None;start=end=0
    for shot in sorted(plan['shots'],key=lambda s:s['start']):
        if shot['image']==active and shot['start']<=end+0.05:end=max(end,shot['end'])
        else:active=shot['image'];start=shot['start'];end=shot['end']
        longest=max(longest,end-start)
    require(longest<=settings['max_continuous_image_seconds'] or reviewed_exception(plan.get('long_image_exception')), '同源图片连续使用过久，须补画面或记录长图复核；拆分运动段不能绕过')
