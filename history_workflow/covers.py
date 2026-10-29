"""Platform-specific cover layouts, independent of video aspect ratio."""
import copy
from .core import now, read, require

DEFAULTS = {
    'version': 3, 'layout_count': 3,
    'targets': {
        'BILIBILI': {'label':'B站横版', 'width':1920, 'height':1080, 'ratio':'16:9',
                     'safe_crop_ratio':'4:3', 'filename':'封面_B站_1920x1080.png'},
        # Preserve the existing target ID so old assets still mean portrait.
        'DOUYIN': {'label':'抖音竖向封面', 'width':1080, 'height':1440, 'ratio':'3:4',
                   'safe_crop_ratio':'9:16', 'filename':'封面_抖音竖向_1080x1440.png'},
        'DOUYIN_LANDSCAPE': {'label':'抖音横向封面', 'width':1440, 'height':1080, 'ratio':'4:3',
                             'safe_crop_ratio':'4:3', 'filename':'封面_抖音横向_1440x1080.png'}},
    'policy':'三套分别构图、同一故事身份与标题；不得拉伸或直接硬裁造成文字、人物缺失。重要文字与人物在安全区。',
    'text_policy': {
        'allowed_roles': ['main_title', 'subtitle'],
        'subtitle_optional': True,
        'extra_text_allowed': False,
        'instruction': '只显示主标题；有副标题时可显示副标题。不得另加来源说明、情境标签、页脚、角标或装饰小字。',
        'forbidden_examples': ['明人笔记里的两幕', '历史情境示意', '历史情景示意'],
        'notes_location': '资料性质与二创说明保留在项目资料和发布说明中，不写在封面上。'
    },
    'verification':'项目交付规格；不是声称平台所有场景只接受此尺寸。发布前按实际上传页复查裁切与提示。',
    'generation_stage':'锁稿后生成；可与手动网页配音独立推进；交付三套并分别实测像素尺寸。'
}


def config(root):
    path = root/'00_项目配置/封面规格配置.json'
    return read(path) if path.exists() else copy.deepcopy(DEFAULTS)


def refresh_plan(episode):
    """Explicitly adopt current defaults without rewriting historical snapshots."""
    previous = episode.s.get('cover_plan')
    current = config(episode.root)
    if previous == current:
        return {'changed': False, 'plan': current}
    episode.s.setdefault('cover_plan_history', []).append({'time': now(), 'plan': copy.deepcopy(previous)})
    episode.s['cover_plan'] = copy.deepcopy(current)
    # Cover scope changed; the rendered video itself is not modified.
    episode.s['handoff'] = episode.s['accepted'] = None
    episode.save('显式更新本集封面规格，历史快照保留；新增目标仍需实际图片')
    return {'changed': True, 'plan': current, 'delivery': delivery_status(episode.s)}


def delivery_status(state):
    plan = state.get('cover_plan') or DEFAULTS
    targets = {}
    for target, spec in plan['targets'].items():
        accepted = [aid for aid, a in state.get('assets', {}).items()
                    if a.get('kind') == 'cover' and a.get('cover_target') == target
                    and not a.get('stale') and a.get('review')
                    and (a.get('width'), a.get('height')) == (spec['width'], spec['height'])]
        targets[target] = {'label': spec['label'], 'filename': spec['filename'],
                           'width': spec['width'], 'height': spec['height'],
                           'asset_ids': accepted, 'ready': bool(accepted)}
    return {'status': 'COMPLETE' if all(t['ready'] for t in targets.values()) else 'INCOMPLETE',
            'required_count': len(targets), 'ready_count': sum(t['ready'] for t in targets.values()),
            'targets': targets, 'note': '基于当前素材登记及审核；文件完整性由交付阶段另行校验。'}


def validate(plan, target, width, height):
    targets = plan['targets']
    require(target in targets, '未知封面目标平台')
    spec = targets[target]
    require((width, height)==(spec['width'],spec['height']),
            f"{spec['label']}封面需{spec['width']}x{spec['height']}像素，实测{width}x{height}")
    return {'target':target,'width':width,'height':height,'size_verified':True}
