from types import SimpleNamespace
import copy
import pytest
from history_workflow.core import WorkflowError,read,write
from history_workflow.articles import basis,packet,save_article,check_article,after_completion
from history_workflow.publishing import save_package,check_package

@pytest.fixture
def ep(tmp_path):
    s={'title':'合成故事','status':'PREVIEW_REVIEW','accepted':None,'production_kind':'FORMAL',
       'script':{'text':'合成故事人物甲被指控，钱款没有查实。'},
       'publication':{'title':'合成故事：一场追查'},
       'sources':{'SRC001':{'title':'合成来源（非真实史料）'}}}
    return SimpleNamespace(root=tmp_path,path=tmp_path/'episode',s=s,require_locked=lambda:None,save=lambda event:None)

def content(ep):
    return {'basis_hash':basis(ep),'title':ep.s['publication']['title'],'subtitle':'合成导语',
            'lead':['背景。'],'sections':[{'heading':'未查实的钱款','paragraphs':['<script>不能执行</script> & 合成段落。']}],
            'source_ids':['SRC001'],'tags':['合成故事'],'content_note':'仅作合成测试，指控未查实。',
            'review':{'reviewer':'synthetic','evidence':'合成测试，不冒充真实审稿',
                      'checks':{k:True for k in ['faithful','readable','uncertainty_preserved','humanizer']}}}

def test_completion_creates_real_pending_task_instead_of_fake_finished_article(ep):
    ep.s.update(status='FINAL_ACCEPTED',accepted={'evidence':'synthetic'})
    r=after_completion(ep)
    assert r['status']=='NEEDS_ADAPTATION'
    p=ep.path/'08_发布包/今日头条文字版任务/改写任务.json'
    assert read(p)['basis_hash']==basis(ep)
    assert not ep.s.get('toutiao_article_packages')
    assert ep.s['status']=='FINAL_ACCEPTED'

def test_preview_cannot_be_claimed_as_video_acceptance_and_html_escapes_content(ep):
    r=save_article(ep,content(ep));folder=ep.path/r['directory']
    assert r['status']=='ARTICLE_READY_VIDEO_REVIEW_PENDING'
    html=(folder/'今日头条文字版.html').read_text()
    assert '&lt;script&gt;不能执行&lt;/script&gt;' in html
    assert '复制排版正文' in html and 'id="body"' in html
    data=read(folder/'文章数据.json')
    assert data['upload']['state']=='NOT_UPLOADED'
    assert not data['video_accepted']
    ep.s.update(status='FINAL_ACCEPTED',accepted={'evidence':'synthetic'})
    with pytest.raises(WorkflowError,match='过期'):check_article(ep)
    ready=after_completion(ep)
    assert ready['status']=='READY_FOR_MANUAL_UPLOAD'
    assert (folder/'今日头条文字版.md').exists()

def test_article_requires_current_sources_title_and_actual_review(ep):
    old=content(ep);ep.s['script']['text']='另一故事。'
    with pytest.raises(WorkflowError,match='当前锁稿'):save_article(ep,old)
    d=content(ep);d['title']='不同标题'
    with pytest.raises(WorkflowError,match='标题'):save_article(ep,d)
    d=content(ep);d['source_ids']=['MISSING']
    with pytest.raises(WorkflowError,match='来源'):save_article(ep,d)
    d=content(ep);d['review']['checks']['uncertainty_preserved']=False
    with pytest.raises(WorkflowError,match='审核'):save_article(ep,d)

def test_publication_pack_contains_article_and_article_edits_invalidate_package(ep):
    first=save_article(ep,content(ep));r=save_package(ep,{'body':'正文','short_body':'短文','content_note':'合成测试'})
    folder=ep.path/r['directory']/'今日头条文字版'
    assert (folder/'今日头条文字版.md').is_file() and (folder/'文章数据.json').is_file()
    check_package(ep)
    d=content(ep);d['lead']=['修改后的背景。'];save_article(ep,d)
    with pytest.raises(WorkflowError,match='过期'):check_package(ep)
    current=check_article(ep);write(ep.path/current['files'][0]['path'],'tampered')
    with pytest.raises(WorkflowError,match='被修改'):check_article(ep)
    assert (ep.path/first['directory']/'今日头条文字版.md').exists()

def test_sample_does_not_automatically_create_article_task(ep):
    ep.s['production_kind']='SAMPLE'
    assert after_completion(ep)['status']=='DISABLED'
    assert 'toutiao_article_task' not in ep.s
