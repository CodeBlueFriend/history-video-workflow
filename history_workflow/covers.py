"""Platform-specific cover layouts, independent of video aspect ratio."""
import copy
from .core import now, read, require

ALIASES = {'BILIBILI':'LANDSCAPE_16_9', 'DOUYIN':'PORTRAIT_3_4', 'DOUYIN_LANDSCAPE':'LANDSCAPE_4_3'}
DEFAULTS = {
    'version': 5, 'layout_count': 4,
    'targets': {
        'LANDSCAPE_16_9': {'label':'通用横屏封面16:9', 'width':1920, 'height':1080, 'ratio':'16:9', 'filename':'通用横屏封面16比9.png'},
        'PORTRAIT_3_4': {'label':'通用竖屏封面3:4', 'width':1080, 'height':1440, 'ratio':'3:4', 'filename':'通用竖屏封面3比4.png'},
        'LANDSCAPE_4_3': {'label':'通用横屏封面4:3', 'width':1440, 'height':1080, 'ratio':'4:3', 'filename':'通用横屏封面4比3.png'},
        'PORTRAIT_9_16': {'label':'通用竖屏封面9:16', 'width':1080, 'height':1920, 'ratio':'9:16', 'filename':'通用竖屏封面9比16.png'}},
    'optional_targets': {},
    'policy':'按比例命名和复用；默认四套，含9:16竖屏。不得拉伸或硬裁造成文字人物缺失。',
    'text_policy': {
        'allowed_roles': ['main_title', 'subtitle'],
        'subtitle_optional': True,
        'extra_text_allowed': False,
        'instruction': '只显示主标题；有副标题时可显示副标题。不得另加来源说明、情境标签、页脚、角标或装饰小字。',
        'forbidden_examples': ['明人笔记里的两幕', '历史情境示意', '历史情景示意'],
        'notes_location': '资料性质与二创说明保留在项目资料和发布说明中，不写在封面上。'
    },
    'verification':'通用交付规格；具体平台发布时检查上传页及实际裁切。',
    'generation_stage':'锁稿后可与配音并行；按启用规格逐套构图、实测像素。'
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
                    if a.get('kind') == 'cover' and ALIASES.get(a.get('cover_target'), a.get('cover_target')) == ALIASES.get(target, target)
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
    target = target if target in targets else ALIASES.get(target, target)
    require(target in targets, '未知封面目标平台')
    spec = targets[target]
    require((width, height)==(spec['width'],spec['height']),
            f"{spec['label']}封面需{spec['width']}x{spec['height']}像素，实测{width}x{height}")
    return {'target':target,'width':width,'height':height,'size_verified':True}
