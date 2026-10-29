from copy import deepcopy
import pytest
from history_workflow.core import initialize,new_episode,Episode,WorkflowError
from history_workflow.visuals import DEFAULTS,check,report
from history_workflow.budget import preflight,DEFAULTS as BUDGET


def state():
    scenes=[{'id':f'V{i}','role':r,'paragraphs':[f'P{i}'],'image':f'IMG{i}',
             'description':'合成关键情节','reason':'测试映射'} for i,r in enumerate(DEFAULTS['images']['required_roles'])]
    assets={s['image']:{'kind':'image','paragraphs':s['paragraphs']} for s in scenes}
    plan={'critical_scenes':scenes,'shots':[{'image':s['image'],'paragraphs':s['paragraphs'],'start':i*40,'end':(i+1)*40} for i,s in enumerate(scenes)],
          'image_density_exception':{'reviewer':'synthetic','reason':'合成测试，四个关键画面足以验证映射','evidence':'不代表真实成片评审','accepted':True}}
    s={'visual_policy':deepcopy(DEFAULTS),'production_kind':'FORMAL','estimate':{'video_seconds':900},
       'script':{'paragraphs':[{'id':f'P{i}'} for i in range(4)]},'assets':assets}
    return s,plan


def test_new_formal_defaults_and_hour_limit(tmp_path):
    initialize(tmp_path);e=Episode(tmp_path,new_episode(tmp_path,'时长规划')['episode'])
    assert e.s['range']==[900,3600] and e.s['visual_policy']==DEFAULTS
    with pytest.raises(WorkflowError,match='60分钟'):new_episode(tmp_path,'超长',900,3601)


def test_resource_budget_scales_with_words_not_audio():
    a=preflight({'episode':'测试','script':{'text':'甲'*2700}},BUDGET)
    b=preflight({'episode':'测试','script':{'text':'甲'*10800}},BUDGET)
    assert a['workload']['body_images']==23 and b['workload']['body_images']==91


def test_critical_pictures_must_cover_actual_script_and_shots():
    s,p=state();check(s,p)
    bad=deepcopy(p);bad['critical_scenes'].pop()
    with pytest.raises(WorkflowError,match='开场'):check(s,bad)
    bad=deepcopy(p);bad['shots'].pop()
    with pytest.raises(WorkflowError,match='未实际用于'):check(s,bad)
    bad=deepcopy(p);bad['critical_scenes'][1]['image']='IMG0'
    with pytest.raises(WorkflowError,match='独立源图片'):check(s,bad)
    bad=deepcopy(p);bad.pop('image_density_exception')
    with pytest.raises(WorkflowError,match='正文图片不足'):check(s,bad)


def test_splitting_same_image_motion_cannot_bypass_long_hold_review():
    s,p=state();p['shots']=[{'image':'IMG0','paragraphs':['P0'],'start':0,'end':80},
                            {'image':'IMG0','paragraphs':['P0'],'start':80,'end':160}]+p['shots'][1:]
    for i,shot in enumerate(p['shots'][2:]):shot.update(start=160+40*i,end=200+40*i)
    with pytest.raises(WorkflowError,match='同源图片'):check(s,p,timed=True)
    p['long_image_exception']={'reviewer':'synthetic','reason':'合成复核','evidence':'合成素材','accepted':True}
    check(s,p,timed=True)
    assert report({'plan':p})['status']=='LEGACY_NOT_ADOPTED'
