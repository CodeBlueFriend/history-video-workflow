from copy import deepcopy
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import pytest
from history_workflow.core import WorkflowError, write, read
from history_workflow.publishing import DEFAULT_PLATFORM_IDS, build, save_package, check_package
from history_workflow.tags import DEFAULTS, import_snapshot, match, validate_snapshot

CLOCK=datetime(2026,10,29,12,tzinfo=timezone.utc)

def snapshot():
    stamp=CLOCK.isoformat()
    return {'schema':1,'retrieved_at':stamp,'platforms':{p:{'status':'NOT_FOUND','query':p+' 热门话题','note':'合成测试，未取到','items':[]} for p in DEFAULT_PLATFORM_IDS}}

def item(**kw):
    return {'tag':'张居正','kind':'HASHTAG','source_kind':'OFFICIAL', 'url':'https://www.douyin.com/topic/test',
            'observed_at':CLOCK.isoformat(), 'trend_at':CLOCK.isoformat(),
            'keywords':['张居正'], 'evidence':'合成测试，非真实热门标签', **kw}

def test_snapshot_covers_all_ten_platforms_and_preserves_failures(tmp_path):
    data=snapshot(); data['retrieved_at']=datetime.now(timezone.utc).isoformat()
    a=import_snapshot(tmp_path,data); import_snapshot(tmp_path,data)
    assert len(list((tmp_path/'02_公共素材库/平台热点库/历史快照').glob('*.json')))==2
    assert read(a['saved'])['platforms']['ALIPAY']['status']=='NOT_FOUND'
    data['platforms'].pop('ALIPAY')
    with pytest.raises(WorkflowError,match='10个平台'):validate_snapshot(data,CLOCK)

def test_do_not_invent_hot_matches_from_unrelated_old_unverified_or_search_topics():
    data=snapshot(); data['platforms']['DOUYIN']['items']=[
        item(tag='游戏',keywords=['游戏']), item(tag='张居正旧话题',trend_at=(CLOCK-timedelta(days=8)).isoformat()),
        item(tag='张居正热搜',kind='SEARCH_TREND'), item(tag='张居正第三方',source_kind='THIRD_PARTY'),
        item(tag='张居正过期活动',valid_until=(CLOCK-timedelta(seconds=1)).isoformat()), item()]
    validate_snapshot(data,CLOCK)
    result=match({'script':{'text':'张居正死后遭抄家，万历下令。'}},DEFAULTS,data,['DOUYIN'],clock=CLOCK)['platforms']['DOUYIN']
    assert len(result['rejected'])==5
    assert len(result['hot_matches'])==1
    assert '张居正' in result['tags'] and '历史故事' in result['tags']
    assert '游戏' not in result['tags']

def test_hot_requires_real_board_time_and_official_host():
    data=snapshot(); data['platforms']['DOUYIN']['items']=[item(url='https://douyin.com.example.org/fake')]
    with pytest.raises(WorkflowError,match='官方来源'):validate_snapshot(data,CLOCK)
    data['platforms']['DOUYIN']['items']=[item()]; data['platforms']['DOUYIN']['items'][0].pop('trend_at')
    with pytest.raises(WorkflowError,match='时间'):validate_snapshot(data,CLOCK)
    data['retrieved_at']=(CLOCK+timedelta(days=1)).isoformat()
    with pytest.raises(WorkflowError,match='未来'):validate_snapshot(data,CLOCK)

def test_user_profile_and_keyword_evidence_are_used_not_unrelated_copy_tags():
    settings={**DEFAULTS,'fixed_tags':['历史说书'],'content_rules':[{'tag':'清朝故事','keywords':['雍正']}]}
    result=match({'script':{'text':'雍正与年羹尧的遭遇。'}},settings,None,['DOUYIN'],['不相关'],CLOCK)
    assert result['platforms']['DOUYIN']['tags']==['历史说书','清朝故事']
    assert result['platforms']['DOUYIN']['fresh'] is False

def test_library_update_invalidates_package_and_text_is_merged(tmp_path):
    e=SimpleNamespace(root=tmp_path,path=tmp_path/'ep',s={'title':'测试','script':{'text':'张居正死后抄家。'}},require_locked=lambda:None,save=lambda event:None)
    copy={'body':'测试正文','short_body':'短文','content_note':'合成测试','tags':['张居正']}
    record=save_package(e,copy)
    folder=e.path/record['directory']
    assert (folder/'发布资料汇总.md').exists()
    assert not list(folder.glob('*_发布文案.txt'))
    assert len(build(e)['platforms'])==10
    data=snapshot(); data['retrieved_at']=datetime.now(timezone.utc).isoformat()
    import_snapshot(tmp_path,data)
    with pytest.raises(WorkflowError,match='过期'):check_package(e)
