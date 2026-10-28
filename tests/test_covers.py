import pytest
from history_workflow.core import Episode, WorkflowError, initialize, new_episode, write
from history_workflow.covers import DEFAULTS, config, validate
from history_workflow.budget import DEFAULTS as BUDGET, preflight


def test_new_episode_snapshots_two_cover_layouts(tmp_path):
    initialize(tmp_path)
    name = new_episode(tmp_path, '封面规格继承')['episode']
    e = Episode(tmp_path, name)
    assert e.s['cover_plan'] == DEFAULTS
    changed = config(tmp_path)
    changed['targets']['BILIBILI']['width'] = 1280
    write(tmp_path / '00_项目配置/封面规格配置.json', changed)
    assert Episode(tmp_path, name).s['cover_plan']['targets']['BILIBILI']['width'] == 1920
    next_name = new_episode(tmp_path, '另一集')['episode']
    assert Episode(tmp_path, next_name).s['cover_plan']['targets']['BILIBILI']['width'] == 1280


def test_cover_pixel_validation_rejects_other_layout():
    assert validate(DEFAULTS, 'DOUYIN', 1080, 1440)['size_verified']
    with pytest.raises(WorkflowError):
        validate(DEFAULTS, 'DOUYIN', 1920, 1080)
    with pytest.raises(WorkflowError):
        validate(DEFAULTS, 'UNKNOWN', 1080, 1440)


def test_budget_uses_declared_cover_layout_count():
    state = {'episode':'预算', 'script':{'text':'字'*3600}, 'cover_plan':DEFAULTS}
    result = preflight(state, BUDGET)
    assert result['workload']['covers'] == 2
