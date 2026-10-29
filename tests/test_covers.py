import pytest
from history_workflow.core import Episode, WorkflowError, initialize, new_episode, write
from history_workflow.covers import DEFAULTS, config, validate, refresh_plan, delivery_status
from history_workflow.budget import DEFAULTS as BUDGET, preflight


def test_new_episode_snapshots_three_cover_layouts(tmp_path):
    initialize(tmp_path)
    name = new_episode(tmp_path, '封面规格继承')['episode']
    e = Episode(tmp_path, name)
    assert e.s['cover_plan'] == DEFAULTS
    changed = config(tmp_path)
    changed['targets']['LANDSCAPE_16_9']['width'] = 1280
    write(tmp_path / '00_项目配置/封面规格配置.json', changed)
    assert Episode(tmp_path, name).s['cover_plan']['targets']['LANDSCAPE_16_9']['width'] == 1920
    next_name = new_episode(tmp_path, '另一集')['episode']
    assert Episode(tmp_path, next_name).s['cover_plan']['targets']['LANDSCAPE_16_9']['width'] == 1280


def test_cover_pixel_validation_rejects_other_layout():
    assert validate(DEFAULTS, 'DOUYIN', 1080, 1440)['size_verified']
    assert validate(DEFAULTS, 'DOUYIN_LANDSCAPE', 1440, 1080)['size_verified']
    with pytest.raises(WorkflowError):
        validate(DEFAULTS, 'DOUYIN', 1920, 1080)
    with pytest.raises(WorkflowError):
        validate(DEFAULTS, 'UNKNOWN', 1080, 1440)
    with pytest.raises(WorkflowError):
        validate(DEFAULTS, 'DOUYIN_LANDSCAPE', 1080, 1440)


def test_budget_uses_declared_cover_layout_count():
    state = {'episode':'预算', 'script':{'text':'字'*3600}, 'cover_plan':DEFAULTS}
    result = preflight(state, BUDGET)
    assert result['workload']['covers'] == 3


def test_existing_episode_refresh_is_explicit_and_preserves_old_assets(tmp_path):
    initialize(tmp_path)
    e = Episode(tmp_path, new_episode(tmp_path, '旧封面快照')['episode'])
    import copy
    old = copy.deepcopy(DEFAULTS)
    old['version'] = 3
    old['targets'] = {'BILIBILI': old['targets']['LANDSCAPE_16_9'], 'DOUYIN': old['targets']['PORTRAIT_3_4']}
    old['layout_count'] = 2
    old['targets']['DOUYIN']['filename'] = '封面_抖音_1080x1440.png'
    e.s['cover_plan'] = old
    e.s['assets']['OLD'] = {'kind':'cover', 'cover_target':'DOUYIN', 'width':1080,
                          'height':1440, 'stale':False, 'review':{'evidence':'合成测试'}}
    e.save('合成旧快照')
    e = Episode(tmp_path, e.s['episode'])
    assert len(e.s['cover_plan']['targets']) == 2
    result = refresh_plan(e)
    assert result['changed'] and result['delivery']['required_count'] == 3
    assert e.s['cover_plan_history'][-1]['plan'] == old
    assert result['delivery']['targets']['PORTRAIT_3_4']['ready']
    assert result['delivery']['targets']['PORTRAIT_3_4']['label'] == '通用竖屏封面3:4'
    assert not result['delivery']['targets']['LANDSCAPE_4_3']['ready']
    assert e.s['assets']['OLD']['cover_target'] == 'DOUYIN'
    assert refresh_plan(e)['changed'] is False


def test_cover_status_does_not_claim_new_layout_from_old_or_stale_covers():
    state = {'cover_plan':DEFAULTS, 'assets':{
        'old':{'kind':'cover','review':True,'width':1440,'height':1080},
        'wrong':{'kind':'cover','cover_target':'DOUYIN_LANDSCAPE','review':True,'width':1080,'height':1440},
        'stale':{'kind':'cover','cover_target':'DOUYIN_LANDSCAPE','review':True,'width':1440,'height':1080,'stale':True}}}
    assert delivery_status(state)['ready_count'] == 0
