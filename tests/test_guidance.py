import json
import pytest
from history_workflow.cli import main


def test_guide_available_before_initialization(tmp_path, capsys):
    root = tmp_path / 'not-created'
    assert main(['--root', str(root), 'startup-guide']) == 0
    output = capsys.readouterr()
    guide = json.loads(output.out)
    assert guide['kind'] == 'RECOMMENDATIONS_ONLY'
    assert any('地方志' in item and '笔记野史' in item for item in guide['items'])
    assert not root.exists()


def test_every_start_prints_advice_without_changing_json_or_requiring_confirmation(tmp_path, capsys):
    root = tmp_path / 'runtime'
    for _ in range(2):
        assert main(['--root', str(root), 'init', '--output-dir', str(tmp_path/'delivery')]) == 0
        output = capsys.readouterr()
        assert json.loads(output.out)['root'] == str(root)
        assert '启动阅读建议' in output.err
        assert '以上为建议项，无需确认' in output.err
    assert not list(root.glob('EP001*'))


def test_help_displays_startup_reading(capsys):
    with pytest.raises(SystemExit) as result:
        main(['--help'])
    assert result.value.code == 0
    assert '先找具体故事' in capsys.readouterr().out


def test_launch_without_command_displays_guide_and_usage(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert 'startup-guide' in output and '先找具体故事' in output
