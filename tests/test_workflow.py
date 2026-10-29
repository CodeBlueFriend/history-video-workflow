"""Synthetic fixtures only; these tests do not validate historical truth or voice quality."""
import copy
import json
import shutil
import wave
from pathlib import Path
import pytest
from history_workflow.core import (Episode, WorkflowError, initialize, new_episode, estimate, ROLES, SCORES, CAPS, FINAL_CHECKS, write, digest)

@pytest.fixture
def ep(tmp_path):
    root = tmp_path/'中文桌面'/'历史故事长篇'
    initialize(root)
    name = new_episode(root, '合成流程测试', 2, 3)['episode']
    e = Episode(root, name)
    e.content('source', {'id':'SRC001','title':'合成测试材料 非史料','genre':'测试','locator':'段一','excerpt':'甲乙丙丁戊己','access':'USER_PROVIDED','obtained_at':'2026-10-28'})
    e.content('claim', {'id':'C001','text':'仅验证软件','sources':['SRC001'],'reliability':'LIMITED','allowed_expression':'测试','reason':'合成样例','paragraphs':['P001']})
    e.content('outline', '合成测试提纲')
    e.content('script', {'text':'甲乙丙丁戊己。','author':'writer'})
    e.timing({'rate':180,'audio_tolerance':0.05})
    return e


def review(e, role='fact', issues=None):
    return {'role':role,'input_hash':e.signature(),'reviewer':'independent reviewer','evidence':'合成测试断言，不代表真实审核','conclusion':'PASS','issues':issues or [],'scores':{k:{'score':v,'reason':'合成测试'} for k,v in SCORES.items()},'checks':{k:True for k in ('time','identity','knowledge','causality','transition','repetition','promise')}}


def lock(e):
    for role in ROLES:
        e.review(review(e, role))
    e.lock()


def issue(severity='P0', factual=True):
    return {'id':'I001','paragraph':'P001','quote':'甲','severity':severity,'factual':factual,'description':'合成问题','evidence':'测试证据','repair':'测试修改','acceptance':'核对测试结果'}


def wav(path, seconds=2):
    with wave.open(str(path),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000)
        w.writeframes(b'\x00\x01'*int(8000*seconds))
    return path


def imported(e, tmp_path):
    from PIL import Image
    lock(e)
    e.audio_package({'voice':'SYNTHETIC_NOT_USER_VOICE','settings':{'speed':1},'limit':100})
    audio=wav(tmp_path/'synthetic.wav')
    image=tmp_path/'synthetic.png'; Image.new('RGB',(160,90),'gray').save(image)
    for kind, aid, file in [('audio','A001',audio),('image','IMG001',image),('cover','COVER001',image)]:
        e.asset({'kind':kind,'id':aid,'file':str(file),'source':'合成测试','rights':'仅测试','confirmed_mapping':True,'scene':'合成矩形','paragraphs':['P001']})
        keys={'audio':['no_omission','no_repeat','no_truncation','voice_preserved'],'image':['identity','era','safe_motion','subtitle_space'],'cover':['consistency','readability','identity','rights']}[kind]
        e.verify_asset({'id':aid,'sha256':e.s['assets'][aid]['sha256'],'reviewer':'test fixture','evidence':'仅断言测试','checks':{k:True for k in keys}})
    shot={'id':'K001','image':'IMG001','paragraphs':['P001'],'start':0,'end':2,'motion':'push','purpose':'测试运动','check_method':'合成测试','time_basis':'AUDIO_VERIFIED','anchor_evidence':'测试WAV时长','start_crop':[0,0,1,1],'end_crop':[0.01,0.01,.98,.98],'safety_review':'仅测试'}
    e.set_plan({'responsible':'test','shots':[shot],'transitions':[]})
    return e


def test_timing_units_and_pauses():
    assert estimate('字'*5400,{'rate':180})['video_seconds']==1800
    assert estimate('字'*5400,{'rate':180,'extra_pause':60,'pause_excluded_from_sample':True})['video_seconds']==1860
    with pytest.raises(WorkflowError): estimate('字'*5400,{'rate':180,'extra_pause':60})
    with pytest.raises(WorkflowError): estimate('公元208年',{'rate':180})
    assert estimate('公元208年',{'rate':180,'readings':{'208':'二百零八'}})['characters']==7


def test_project_editing_preferences_inherit_and_snapshot(ep):
    path = ep.root / '00_项目配置/剪辑规则配置.json'
    settings = json.loads(path.read_text())
    settings['captions'] = {'font_size_px_at_1080p': 60}
    settings['motion']['default_scale_change_percentage_points'] = 12
    write(path, settings)
    name = new_episode(ep.root, '参数继承测试', 2, 3)['episode']
    child = Episode(ep.root, name)
    assert child.s['editing_defaults'] == settings
    lock(ep)
    document = ep.document('PLAN')
    snapshot = next(f for f in document['files'] if f['path'].endswith('结构快照.json'))
    frozen = json.loads((ep.path / snapshot['path']).read_text())
    assert frozen['editing_defaults'] == settings
    settings['captions']['font_size_px_at_1080p'] = 64
    write(path, settings)
    assert json.loads((ep.path / snapshot['path']).read_text())['editing_defaults']['captions']['font_size_px_at_1080p'] == 60


def test_incomplete_review_blocks(ep):
    with pytest.raises(WorkflowError): ep.lock()


def test_p0_never_waived(ep):
    ep.review(review(ep,issues=[issue()]))
    with pytest.raises(WorkflowError):
        ep.resolve({'id':'I001','input_hash':ep.signature(),'reviewer':'other','evidence':'测试','outcome':'ACCEPTED','user_acceptance':'接受'})
    for role in ROLES: ep.review(review(ep,role))
    with pytest.raises(WorkflowError): ep.lock()


def test_p1_acceptance_record(ep):
    ep.review(review(ep,issues=[issue('P1',False)]))
    ep.resolve({'id':'I001','input_hash':ep.signature(),'reviewer':'other','evidence':'复审范围','outcome':'ACCEPTED','user_acceptance':'仅接受此风格取舍'})
    lock(ep)
    assert ep.s['lock']
    assert ep.s['issues']['I001']['history'][0]['user_acceptance']


def test_two_failed_repairs_block(ep):
    ep.review(review(ep,issues=[issue()]))
    data={'id':'I001','input_hash':ep.signature(),'reviewer':'other','evidence':'未修复','outcome':'FAILED'}
    ep.resolve(data); ep.resolve(data)
    assert ep.s['status']=='BLOCKED_USER_DECISION'
    with pytest.raises(WorkflowError): ep.resolve(data)


def test_writer_cannot_review(ep):
    data=review(ep);data['reviewer']='writer'
    with pytest.raises(WorkflowError): ep.review(data)


def test_review_issue_can_span_existing_paragraphs(ep):
    ep.content('script', {'text': '甲乙。\n\n丙丁。', 'author': 'writer'})
    cross = {**issue(), 'paragraph': 'P001/P002'}
    ep.review(review(ep, issues=[cross]))
    assert ep.s['issues']['I001']['paragraph'] == 'P001/P002'
    invalid = {**cross, 'paragraph': 'P001/P999'}
    with pytest.raises(WorkflowError, match='问题段落不存在'):
        ep.review(review(ep, issues=[invalid]))


def test_packet_does_not_leak_author_evaluation(ep):
    ep.s['script']['self_score']=100
    p=ep.review_packet('fact')
    raw=Path(p['packet']).read_text()
    assert 'self_score' not in raw and 'writer' not in raw


def test_lock_changes_invalidate(ep):
    lock(ep)
    with pytest.raises(WorkflowError): ep.content('script',{'text':'新内容','author':'writer'})
    ep.content('script',{'text':'新内容','author':'writer'},'确认重开：下游需重审')
    assert ep.s['lock'] is None and ep.s['reviews']=={}


def test_cover_change_preserves_audio(ep,tmp_path):
    imported(ep,tmp_path)
    tasks=copy.deepcopy(ep.s['audio_tasks']); audio=copy.deepcopy(ep.s['assets']['A001'])
    ep.asset({'kind':'cover','id':'COVER001','file':str(tmp_path/'synthetic.png'),'source':'测试','rights':'测试','confirmed_mapping':True})
    assert ep.s['audio_tasks']==tasks and ep.s['assets']['A001']==audio
    assert ep.s['assets']['COVER001']['review'] is None


def test_audio_explicit_mapping(ep,tmp_path):
    lock(ep)
    with pytest.raises(WorkflowError): ep.asset({'kind':'audio','id':'A001','file':str(wav(tmp_path/'a.wav')),'source':'测试','rights':'测试','confirmed_mapping':True})


def test_coverage_gap_and_overlap(ep,tmp_path):
    imported(ep,tmp_path)
    assert ep.coverage()['covered_seconds']==2
    ep.s['plan']['shots'][0]['start']=0.5
    with pytest.raises(WorkflowError): ep.coverage()


def test_static_exception(ep,tmp_path):
    imported(ep,tmp_path)
    ep.s['plan']['shots'][0]['motion']='static'
    with pytest.raises(WorkflowError): ep.coverage()


def test_mutated_asset_rejected(ep,tmp_path):
    imported(ep,tmp_path)
    (ep.path/ep.s['assets']['A001']['path']).write_bytes(b'broken')
    with pytest.raises(WorkflowError): ep.audio_ready()


def test_resume_move_and_docs(ep,tmp_path):
    imported(ep,tmp_path)
    doc=ep.document('TIMED')
    assert len(doc['files'])==5
    import zipfile
    docx=ep.path/doc['files'][0]['path']
    with zipfile.ZipFile(docx) as z: assert b'K001' in z.read('word/document.xml')
    moved=tmp_path/'moved';shutil.copytree(ep.root,moved)
    restored=Episode(moved,ep.s['episode'])
    assert restored.coverage()['audio_seconds']==2
    assert restored.s==ep.s


def test_handoff_requires_real_tool_record(ep,tmp_path):
    imported(ep,tmp_path)
    with pytest.raises(WorkflowError): ep.handoff()


def test_export_is_not_acceptance(ep,tmp_path,monkeypatch):
    imported(ep,tmp_path)
    write(ep.root/'00_项目配置/已核验工具.json',{'name':'SYNTHETIC_FAKE_EDITOR','version':'test','tester':'test','checks':{k:{'passed':True,'evidence':'合成测试 不是实际验证'} for k in CAPS}})
    result=ep.handoff()
    assert Path(result['archive']).exists()
    video=tmp_path/'synthetic.mp4';video.write_bytes(b'fake media for mocked probe')
    monkeypatch.setattr('history_workflow.core.duration',lambda *a,**k:2.1)
    ep.register_export({'file':str(video),'project_url':'https://example.invalid/synthetic','settings':{'note':'test'},'executed_by':'synthetic'})
    assert ep.s['status']=='PREVIEW_REVIEW' and ep.s['accepted'] is None
    with pytest.raises(WorkflowError): ep.accept({'video_hash':ep.s['export']['video']['sha256']})
    ep.accept({'video_hash':ep.s['export']['video']['sha256'],'reviewer':'test','evidence':'test','checks':{k:True for k in FINAL_CHECKS},'execution_matches_document':True})
    assert ep.s['status']=='FINAL_ACCEPTED' and ep.s['documents'][-1]['stage']=='FINAL'
    assert ep.s['toutiao_article_task']['status']=='NEEDS_ADAPTATION'


def test_non_destructive_init(ep):
    file=ep.root/'使用说明.txt';file.write_text('user modified')
    initialize(ep.root)
    assert file.read_text()=='user modified'


def test_path_escape(ep):
    from history_workflow.core import inside
    with pytest.raises(WorkflowError): inside(ep.root,'../../escape')
    with pytest.raises(WorkflowError): new_episode(ep.root,'../bad')


def test_changed_voice_invalidates_old_audio(ep,tmp_path):
    imported(ep,tmp_path)
    ep.audio_package({'voice':'new','settings':{'speed':1},'limit':100})
    with pytest.raises(WorkflowError): ep.audio_ready()


def test_lock_review_tampering_blocks_production(ep):
    lock(ep)
    ep.review(review(ep,'fact',issues=[issue()]))
    with pytest.raises(WorkflowError): ep.audio_package({'voice':'test','settings':{'speed':1},'limit':100})


def test_claim_unknown_paragraph(ep):
    ep.s['claims']['C001']['paragraphs']=['P999']
    for role in ROLES: ep.review(review(ep,role))
    ep.timing({'rate':180})
    with pytest.raises(WorkflowError): ep.lock()


def test_transition_overlap_counts_union(ep,tmp_path):
    imported(ep,tmp_path)
    first=ep.s['plan']['shots'][0]
    first['end']=1.2
    second=copy.deepcopy(first);second.update(id='K002',start=1.0,end=2.0)
    ep.s['plan']['shots'].append(second)
    ep.s['plan']['transitions']=[{'from':'K001','to':'K002','overlap':0.2,'semantic_reason':'测试句末','audio_continuity':'保持原音轨','ghosting_review':'测试复核'}]
    assert ep.coverage()['covered_seconds']==2.0
    ep.s['plan']['transitions'][0]['overlap']=0.8
    with pytest.raises(WorkflowError):ep.coverage()


def test_orphan_document_does_not_block_resume(ep,tmp_path):
    imported(ep,tmp_path)
    folder=ep.path/'05_AI剪辑交接包/剪辑文档/历史版本/v002_TIMED_interrupted'
    folder.mkdir()
    (folder/'partial.txt').write_text('interrupted')
    record=ep.document('TIMED')
    assert record['version']==2 and folder.exists()


def test_production_delivery_excludes_application(ep,tmp_path):
    imported(ep,tmp_path)
    output=tmp_path/'desktop'/'资料'
    initialize(ep.root,output)
    # Cover metadata imported after lock makes the draft publishing package stale.
    from history_workflow.publishing import save_package
    save_package(ep)
    first=ep.deliver()
    target=Path(first['directory'])
    assert (target/'02_故事文稿/口播定稿.txt').exists()
    assert (target/ep.s['assets']['A001']['path']).exists()
    assert not (target/'00_项目记录').exists()
    assert not (target/'00_项目配置').exists()
    assert not (target/'EP000_模板').exists()
    marker=target/'用户备注.txt';marker.write_text('保留')
    second=ep.deliver()
    assert second['directory']!=first['directory'] and marker.read_text()=='保留'


def test_default_runtime_is_not_desktop(tmp_path):
    from history_workflow.core import default_root
    assert default_root()==Path(__file__).resolve().parents[1]/'production'
    initialize(tmp_path/'runtime',tmp_path/'desktop')
    assert not (tmp_path/'desktop').exists()
    with pytest.raises(WorkflowError):initialize(tmp_path/'runtime',tmp_path/'runtime'/'outputs')


def test_real_prewrite_reviews_and_version_invalidation(tmp_path):
    root=tmp_path/'project';initialize(root)
    name=new_episode(root,'前置审核',1,10)['episode']
    e=Episode(root,name)
    e.content('source',{'id':'SRC001','title':'材料','genre':'史书','locator':'段落','excerpt':'摘录','access':'READ','obtained_at':'2026-10-28'})
    e.content('claim',{'id':'C001','text':'主张','sources':['SRC001'],'reliability':'LIMITED','allowed_expression':'归因','reason':'依据','paragraphs':['P001']})
    data={'role':'evidence','input_hash':e.stage_signature('evidence'),'reviewer':'reviewer','evidence':'已核查','conclusion':'PASS','issues':[]}
    e.stage_review(data)
    assert e.s['script'] is None
    e.content('outline','实际提纲')
    outline={**data,'role':'outline','input_hash':e.stage_signature('outline')}
    e.stage_review(outline)
    e.content('script',{'text':'甲乙丙丁戊己。','author':'writer'})
    e.timing({'rate':180})
    for role in ('fact','narrative','oral','coherence','clean'):e.review(review(e,role))
    assert e.blockers()==[]
    e.s['sources']['SRC001']['excerpt']='修改后的证据'
    with pytest.raises(WorkflowError):e.stage_review(outline)
    assert any('evidence' in b for b in e.blockers())


def test_user_recording_can_arrive_without_tts_metadata(ep, tmp_path):
    lock(ep)
    data = {'file': str(wav(tmp_path/'user.wav')), 'confirmed_mapping': True,
            'source': 'user supplied test recording', 'rights': 'test fixture'}
    ep.receive_audio(data)
    assert ep.s['audio_tasks'][0]['voice'] is None
    assert ep.s['audio_tasks'][0]['metadata_status'] == 'PENDING_CONFIRMATION'
    assert ep.s['assets']['A001']['seconds'] == 2
    assert ep.s['assets']['A001']['review'] is None
    with pytest.raises(WorkflowError): ep.audio_ready()
    with pytest.raises(WorkflowError, match='已有配音任务'): ep.receive_audio(data)


def test_images_do_not_wait_for_audio(ep, tmp_path):
    from PIL import Image
    lock(ep)
    p = tmp_path/'image.png'
    Image.new('RGB', (320,180), 'gray').save(p)
    for kind, aid in [('image','IMG001'), ('cover','COVER001')]:
        ep.asset({'kind':kind, 'id':aid, 'file':str(p), 'source':'test',
                  'rights':'test', 'confirmed_mapping':True,
                  'scene':'test scene', 'paragraphs':['P001']})
    assert not ep.s['audio_tasks']
    assert set(ep.s['assets']) == {'IMG001','COVER001'}
