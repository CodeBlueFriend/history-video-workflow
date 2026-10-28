import copy
import pytest
from history_workflow.budget import DEFAULTS, preflight, start_run, finish_run
from history_workflow.core import WorkflowError, initialize, new_episode, Episode

def state():
    return {'episode':'EP001_预算测试','script':{'text':'字'*5400},'assets':{'A001':{'seconds':10}}}

def test_text_only_and_manual_tts_exclusion():
    s=state(); a=preflight(s,DEFAULTS);s['assets']['A001']['seconds']=99999
    b=preflight(s,DEFAULTS)
    assert a['estimated_video_seconds']==b['estimated_video_seconds']==1804.5
    assert a['characters']==5400 and a['audio_duration_used'] is False
    assert a['manual_audio_generation']=='EXCLUDED'
    assert a['estimated_cost'] is None and a['production_seconds'] is None

def test_complete_price_calculation_and_partial_unknown():
    c=copy.deepcopy(DEFAULTS); c['prices'].update(llm_input_per_million_tokens=2,llm_output_per_million_tokens=6,per_image_attempt=.5,render_per_video_minute=.2)
    a=preflight(state(),c);u=a['workload']
    assert a['estimated_cost']==pytest.approx(u['llm_input_tokens']/1e6*2+u['llm_output_tokens']/1e6*6+u['image_attempts']*.5+u['render_video_minutes']*.2)
    c['prices']['render_per_video_minute']=None
    assert preflight(state(),c)['estimated_cost'] is None

def test_invalid_estimates_and_readings():
    c=copy.deepcopy(DEFAULTS);c['duration']['characters_per_minute']=float('nan')
    with pytest.raises(WorkflowError):preflight(state(),c)
    c=copy.deepcopy(DEFAULTS);s=state();s['script']['text']='公元208年'
    with pytest.raises(WorkflowError):preflight(s,c)
    c['duration']['readings']={'208':'二百零八'}
    assert preflight(s,c)['characters']==7

def test_run_receipts_and_unknown_actual_cost(tmp_path):
    initialize(tmp_path);name=new_episode(tmp_path,'预算测试')['episode'];ep=Episode(tmp_path,name)
    ep.s['script']={'text':'甲乙丙'}
    run=start_run(ep)
    with pytest.raises(WorkflowError):start_run(ep)
    with pytest.raises(WorkflowError):finish_run(ep,{'usage':{'input_tokens':100}})
    result=finish_run(ep,{'usage':{'input_tokens':100},'evidence':'test receipt'})
    assert result['actual_cost'] is None
    assert result['wall_seconds']>=0 and result['id']==run['id']
    with pytest.raises(WorkflowError):finish_run(ep,{})

def test_current_shot_plan_overrides_rough_image_count():
    s=state();s['plan']={'shots':[{'image':'IMG001'},{'image':'IMG001'},{'image':'IMG002'}]}
    p=preflight(s,DEFAULTS)
    assert p['workload']['body_images']==2
    assert p['image_count_basis']=='CURRENT_SHOT_PLAN'
