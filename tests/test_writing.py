from history_workflow.core import initialize, new_episode, Episode, write
from history_workflow.writing import DEFAULTS, config


def test_new_episode_freezes_writing_guidance(tmp_path):
    initialize(tmp_path)
    a = Episode(tmp_path, new_episode(tmp_path, '旧集')['episode'])
    changed = config(tmp_path)
    changed['opening'] = ['先说明背景和人物关系']
    write(tmp_path/'00_项目配置/文稿编写规则.json', changed)
    b = Episode(tmp_path, new_episode(tmp_path, '新集')['episode'])
    assert a.s['writing_rules'] == DEFAULTS
    assert b.s['writing_rules'] == changed


def test_review_packets_bind_writing_guidance(tmp_path):
    initialize(tmp_path)
    e = Episode(tmp_path, new_episode(tmp_path, '包测试')['episode'])
    e.content('script', {'text':'合成测试，不是历史内容。', 'author':'fixture'})
    from history_workflow.core import read
    stage = e.stage_packet('evidence')
    final = e.review_packet('narrative')
    assert read(stage['packet'])['writing_rules'] == e.s['writing_rules']
    assert read(final['packet'])['writing_rules'] == e.s['writing_rules']
    before = e.signature()
    old_stage = e.stage_signature('evidence')
    e.s['writing_rules']['voice'] = '修订后的写法'
    assert before != e.signature()
    assert old_stage != e.stage_signature('evidence')


def test_legacy_episode_without_rules_remains_readable(tmp_path):
    initialize(tmp_path)
    e = Episode(tmp_path, new_episode(tmp_path, '旧格式')['episode'])
    e.s.pop('writing_rules')
    e.content('script', {'text':'旧格式合成文本。', 'author':'fixture'})
    from history_workflow.core import read
    assert read(e.review_packet('oral')['packet'])['writing_rules'] == {}
