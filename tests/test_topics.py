import copy
import pytest
from history_workflow.core import initialize, Episode, WorkflowError, read
from history_workflow.topics import save_options, select, add_idea
from history_workflow.cli import main

@pytest.fixture
def setup(tmp_path):
    root=tmp_path/'runtime'; initialize(root)
    data={'id':'batch-1','options':[{'id':str(i),'title':f'候选{i}','summary':'内容范围','angle':'叙事角度'} for i in range(1,4)]}
    save_options(root,data)
    return root,data


def test_selection_preserves_candidate_and_user_idea(setup):
    root,data=setup
    result=select(root,'batch-1','2','重点解释人物选择',120,180)
    e=Episode(root,result['episode'])
    assert e.s['title']=='候选2'
    assert e.s['creative_brief']['selected']==data['options'][1]
    assert e.s['creative_brief']['ideas'][0]['text']=='重点解释人物选择'
    packet=read(e.stage_packet('evidence')['packet'])
    assert packet['creative_brief']==e.s['creative_brief']
    assert not e.s['claims']


def test_idea_invalidates_reviews_and_locked_outputs(setup):
    root,_=setup;e=Episode(root,select(root,'batch-1','1')['episode'])
    before=e.signature();stage=e.stage_signature('evidence')
    e.s.update(lock={'test':True},reviews={'fact':{}},stage_reviews={'evidence':{}},plan={'test':True},export={'file':'old'})
    with pytest.raises(WorkflowError):add_idea(e,'新角度')
    assert e.signature()==before
    add_idea(e,'新角度','用户修改内容要求')
    assert e.signature()!=before and e.stage_signature('evidence')!=stage
    assert e.s['lock'] is None and e.s['plan'] is None and e.s['export'] is None
    assert not e.s['reviews'] and not e.s['stage_reviews']
    add_idea(e,'补充一个反问')
    assert len(e.s['creative_brief']['ideas'])==2


def test_invalid_options_do_not_overwrite(setup):
    root,data=setup
    with pytest.raises(WorkflowError):save_options(root,data)
    with pytest.raises(WorkflowError):select(root,'batch-1','missing')
    for bad in [{'id':'../escape','options':data['options']},{'id':'one','options':data['options'][:1]}, {'id':'dup','options':[data['options'][0]]*2}]:
        with pytest.raises(WorkflowError):save_options(root,bad)
    assert not list(root.glob('EP001*'))


def test_cli_select_and_append(setup,tmp_path,capsys):
    root,_=setup
    assert main(['--root',str(root),'topic-select','batch-1','3','--idea','保留悬念','--minimum','120','--maximum','180'])==0
    f=tmp_path/'idea.txt';f.write_text('补充人物关系',encoding='utf-8')
    assert main(['--root',str(root),'idea','EP001_候选3',str(f)])==0
    assert Episode(root,'EP001_候选3').s['creative_brief']['ideas'][-1]['text']=='补充人物关系'
