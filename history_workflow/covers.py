"""Two platform cover layouts, independent of video aspect ratio."""
import copy
from .core import read, require

DEFAULTS = {
    'version': 2, 'layout_count': 2,
    'targets': {
        'BILIBILI': {'label':'B站横版', 'width':1920, 'height':1080, 'ratio':'16:9',
                     'safe_crop_ratio':'4:3', 'filename':'封面_B站_1920x1080.png'},
        'DOUYIN': {'label':'抖音竖版', 'width':1080, 'height':1440, 'ratio':'3:4',
                   'safe_crop_ratio':'9:16', 'filename':'封面_抖音_1080x1440.png'}},
    'policy':'两套独立构图、同一故事身份与标题；不得拉伸或直接硬裁横版。重要文字与人物在居中安全区。',
    'text_policy': {
        'allowed_roles': ['main_title', 'subtitle'],
        'subtitle_optional': True,
        'extra_text_allowed': False,
        'instruction': '只显示主标题；有副标题时可显示副标题。不得另加来源说明、情境标签、页脚、角标或装饰小字。',
        'forbidden_examples': ['明人笔记里的两幕', '历史情境示意', '历史情景示意'],
        'notes_location': '资料性质与二创说明保留在项目资料和发布说明中，不写在封面上。'
    },
    'verification':'项目交付规格；不是声称平台所有场景只接受此尺寸。发布前按实际上传页复查裁切与提示。',
    'generation_stage':'锁稿后生成；可与手动网页配音独立推进；交付两套并实测像素尺寸。'
}


def config(root):
    path = root/'00_项目配置/封面规格配置.json'
    return read(path) if path.exists() else copy.deepcopy(DEFAULTS)


def validate(plan, target, width, height):
    targets = plan['targets']
    require(target in targets, '未知封面目标平台')
    spec = targets[target]
    require((width, height)==(spec['width'],spec['height']),
            f"{spec['label']}封面需{spec['width']}x{spec['height']}像素，实测{width}x{height}")
    return {'target':target,'width':width,'height':height,'size_verified':True}
