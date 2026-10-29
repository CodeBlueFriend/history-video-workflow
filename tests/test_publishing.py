from types import SimpleNamespace
import pytest
from history_workflow.core import WorkflowError, read, write
from history_workflow.publishing import build, save_package, check_package


@pytest.fixture
def episode(tmp_path):
    state = {'title': '旧文件夹题名', 'script': {'title': '稿件题名', 'text': '合成故事甲乙丙。'},
             'publication': {'title': '视频标题：相同故事'}}
    return SimpleNamespace(root=tmp_path, path=tmp_path/'episode', s=state,
                           require_locked=lambda: None, save=lambda event: None)


def content():
    return {'subtitle': '一句引出故事的吸引句', 'body': '合成故事正文。', 'short_body': '合成短简介。',
            'content_note': '合成测试素材。', 'tags': ['合成故事'], 'pinned_comment': '合成问题？'}


def test_exact_video_title_in_every_platform_and_separate_subtitle(episode):
    bundle = build(episode, content())
    assert bundle['status'] == 'COPY_READY_FOR_PLATFORM_REVIEW'
    assert all(p['title'] == '视频标题：相同故事' for p in bundle['platforms'].values())
    assert all(p['subtitle'] == content()['subtitle'] for p in bundle['platforms'].values())
    with pytest.raises(WorkflowError, match='逐字一致'):
        build(episode, {**content(), 'title': '未经同意的新标题'})


def test_automatic_package_is_explicit_unfilled_draft(episode):
    bundle = build(episode)
    assert bundle['status'] == 'DRAFT_NEEDS_COPY'
    assert bundle['copy']['body'] == ''
    assert bundle['copy']['content_note'] == ''


def test_versions_preserved_and_file_tamper_detected(episode):
    a = save_package(episode, content())
    b = save_package(episode, {**content(), 'body': '第二版合成文案。'})
    assert a['directory'] != b['directory']
    assert read(episode.path/a['directory']/'发布文案.json')['copy']['body'] == '合成故事正文。'
    assert check_package(episode)['version'] == 2
    write(episode.path/b['files'][0]['path'], '外部改写')
    with pytest.raises(WorkflowError, match='文件缺失或被修改'):
        check_package(episode)


def test_title_edit_invalidates_then_regenerates_without_truncation(episode):
    save_package(episode, content())
    episode.s['publication']['title'] = '新视频标题' * 30
    with pytest.raises(WorkflowError, match='过期'):
        check_package(episode)
    record = save_package(episode)
    bundle = read(episode.path/record['directory']/'发布文案.json')
    assert bundle['title'] == '新视频标题' * 30
    assert bundle['copy']['body'] == content()['body']


def test_script_edit_cannot_silently_reuse_previous_copy(episode):
    save_package(episode, content())
    episode.s['script']['text'] = '另一故事，需要重新提炼文案。'
    with pytest.raises(WorkflowError, match='过期'):
        check_package(episode)
    bundle = build(episode)
    assert bundle['status'] == 'DRAFT_NEEDS_COPY' and bundle['copy']['body'] == ''


def test_unknown_platform_and_invalid_tags_rejected(episode):
    with pytest.raises(WorkflowError):
        build(episode, {**content(), 'tags': ['#历史 故事']})
    write(episode.root/'00_项目配置/发布文案配置.json', {'platforms': ['../../elsewhere']})
    with pytest.raises(WorkflowError, match='平台未知'):
        build(episode, content())


def test_generic_cover_package_includes_verified_legacy_cover_and_detects_tamper(episode):
    from PIL import Image
    from history_workflow.covers import DEFAULTS as COVERS
    from history_workflow.core import file_hash
    episode.s['publication'].update(main_title='主标题',subtitle='副标题')
    episode.s['cover_plan']=COVERS
    episode.s['assets']={}
    for i,(target,spec) in enumerate(COVERS['targets'].items()):
        path=episode.path/f'image{i}.png';path.parent.mkdir(parents=True,exist_ok=True)
        Image.new('RGB',(spec['width'],spec['height'])).save(path)
        old={'LANDSCAPE_16_9':'BILIBILI','LANDSCAPE_4_3':'DOUYIN_LANDSCAPE','PORTRAIT_3_4':'DOUYIN','PORTRAIT_9_16':'PORTRAIT_9_16'}[target]
        episode.s['assets'][str(i)]={'kind':'cover','cover_target':old,'main_title':'主标题','subtitle':'副标题',
                                    'path':path.name,'sha256':file_hash(path),'width':spec['width'],'height':spec['height'],'review':True}
    record=save_package(episode,content()); folder=episode.path/record['directory']
    files=list((folder/'封面').glob('*.png'))
    assert len(files)==4 and all('通用' in f.name for f in files)
    assert '待制作/核验' not in (folder/'发布资料汇总.md').read_text()
    files[0].write_bytes(b'changed')
    with pytest.raises(WorkflowError,match='文件缺失或被修改'):check_package(episode)
