import copy
import json
import pytest
from history_workflow.core import Episode, WorkflowError, initialize, new_episode, read
from history_workflow.story_history import check, ensure_distinct, history, record, set_profile
from history_workflow.topics import save_options, select
from history_workflow.cli import main


def story():
    return {'storyline_id':'hongmen-escape','characters':['刘邦','项羽'],'core_event':'鸿门宴刘邦脱身',
            'conflict':'范增主张杀刘邦而刘邦需要脱身','turning_points':['项伯说情','项庄舞剑被阻挡','樊哙入帐','刘邦借口离席'],
            'outcome':'刘邦回到军营张良留下辞谢','aliases':['鸿门宴脱险']}


def other():
    return {'storyline_id':'liubang-first-law','characters':['刘邦'],'core_event':'刘邦入关约法',
            'conflict':'新占领地区需要取得民众信任','turning_points':['宣布约束刑罚和军纪','处理当地秩序'],
            'outcome':'建立初步统治秩序；示例待核'}


@pytest.fixture
def root(tmp_path):
    initialize(tmp_path)
    return tmp_path


def past(root, data=None, rid='past-1'):
    return record(root, {'id':rid,'title':'历史旧作','status':'PRODUCED','evidence':'测试回执，不代表真实史料','story':data or story()})


def test_renamed_title_and_changed_id_cannot_repeat_core_event(root):
    past(root)
    s=story();s['storyline_id']='renamed';s['core_event']='鸿门宴，刘邦脱身！'
    assert check(root,s)['status']=='DUPLICATE'
    with pytest.raises(WorkflowError, match='故事线重复'):
        new_episode(root,'完全不同的标题',story=s)
    assert not list(root.glob('EP001*'))
    s=other();s['aliases']=['鸿门宴脱险']
    assert check(root,s)['status']=='DUPLICATE'


def test_character_reuse_and_different_story_allowed(root):
    past(root)
    assert check(root,other())['status']=='NO_MATCH_FOUND'
    name=new_episode(root,'刘邦的另一件事',story=other())['episode']
    assert history(root)['records'][-1]['episode']==name
    assert check(root,other())['status']=='DUPLICATE'


def test_paraphrase_requires_explicit_plot_difference_review(root):
    past(root)
    s=story();s['storyline_id']='another';s['aliases']=[];s['core_event']='刘邦在鸿门宴上的脱身经过'
    result=check(root,s)
    assert result['status']=='REVIEW_REQUIRED'
    with pytest.raises(WorkflowError, match='疑似重复'):ensure_distinct(result)
    s['distinctness_note']='测试模拟人工核对后的实质差异说明，非实际历史判断'
    ensure_distinct(check(root,s))


def test_same_plot_without_character_field_is_duplicate(root):
    past(root)
    s=story();s['characters']=['刘季','项籍']
    assert check(root,s)['status']=='DUPLICATE'


def test_selection_rechecks_history_after_batch_saved(root):
    data={'id':'batch','options':[{'id':key,'title':title,'summary':'内容','angle':'角度','story':s} for key,title,s in [('A','故事甲',story()),('B','故事乙',other())]]}
    save_options(root,data)
    new_episode(root,'另一项目已先占用此故事',story=story())
    with pytest.raises(WorkflowError, match='故事线重复'):select(root,'batch','A')
    select(root,'batch','B')
    assert len(history(root)['records'])==2


def test_duplicates_within_candidate_batch_and_missing_profile_rejected(root):
    options=[{'id':str(i),'title':str(i),'summary':'内容','angle':'角度','story':story()} for i in range(2)]
    with pytest.raises(WorkflowError, match='故事线重复'):save_options(root,{'id':'dups','options':options})
    options[1]['story']=other();options[0].pop('story')
    with pytest.raises(WorkflowError, match='故事线档案'):save_options(root,{'id':'missing','options':options})


def test_legacy_visibility_and_profile_revision_preserve_history(root):
    name=new_episode(root,'旧项目')['episode'];e=Episode(root,name)
    assert name in history(root)['unprofiled_episodes']
    set_profile(e,story())
    before=e.signature();e.s.update(lock={'test':True},reviews={'fact':{}},stage_reviews={'evidence':{}},plan={'old':True})
    with pytest.raises(WorkflowError):set_profile(e,other())
    set_profile(e,other(),'内容改动')
    assert e.signature()!=before
    assert e.s['lock'] is None and e.s['plan'] is None and not e.s['stage_reviews']
    assert len(e.s['storyline_history'])==1
    assert check(root,story())['status']=='DUPLICATE'
    assert check(root,other())['status']=='DUPLICATE'
    assert not history(root)['unprofiled_episodes']


def test_history_receipts_immutable_and_cli_output(root,tmp_path,capsys):
    p=tmp_path/'old.json';p.write_text(json.dumps({'id':'old','title':'测试历史','status':'PRODUCED','evidence':'合成日志','story':story()}))
    assert main(['--root',str(root),'story-record',str(p)])==0
    assert main(['--root',str(root),'story-record',str(p)])==2
    capsys.readouterr()
    assert main(['--root',str(root),'story-history'])==0
    output=json.loads(capsys.readouterr().out)
    assert output['records'][0]['story']['core_event']==story()['core_event']


def test_late_history_entry_blocks_lock(root):
    e=Episode(root,new_episode(root,'当前项目',story=story())['episode'])
    past(root)
    with pytest.raises(WorkflowError,match='故事线重复'):e.lock()
