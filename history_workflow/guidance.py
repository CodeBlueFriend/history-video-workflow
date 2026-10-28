"""Reusable startup reading; recommendations never gate production commands."""

TITLE = '启动阅读建议：先找具体故事，再形成选题'
RECOMMENDATIONS = (
    '优先选择带名人或与名人有关的故事，从具体遭遇、人物关系和鲜为人知的细节切入。',
    '素材同时覆盖正史、地方志、笔记野史、文集书信、日记年谱、家谱碑传、公案档案、诗话及志怪传说。',
    '两路检索：从姓名、字号、亲友及任职地区向外查；也从借贷、诉讼、考试、夜访等情节反查名人关系。',
    '先记录书库、书目版本和条目卷页，再建故事卡；搜索摘要、目录和OCR不等于已核对原文。',
    '故事卡写清人物目标、阻碍、转折、悬念、结局、名人关系、出处及可二创范围。',
    '准备候选和立项前查看story-history并核对核心事件、冲突、转折和结局：人物可以重复，故事线不能重复；样片和测试不计历史或占用。',
    '逐条判断作者距离、信息来源、版本和转引关系；区分史实、某书记载、传闻、推测与二创。',
    '可先试采30—50张故事卡、筛8—12条线索，再提供约5个候选供用户选择并补充想法；数量可按项目调整。',
    '15—40分钟围绕核心故事组织，按情节容量定长度；有口播稿后按字数预估，手动网页配音耗时费用暂不计入。',
    '逐项记录查阅和复用条件；公开代码与来源目录，第三方全文、影像及现代校注按各自许可处理。',
)


def startup_guide():
    return {'title': TITLE, 'kind': 'RECOMMENDATIONS_ONLY',
            'items': list(RECOMMENDATIONS), 'documentation': 'docs/story-sourcing.md',
            'note': '供每次启动阅读；不要求确认，不代表已执行检索、核验或故事采集。'}


def startup_text():
    return '\n'.join((TITLE, *(f'{i}. {text}' for i, text in enumerate(RECOMMENDATIONS, 1)),
                      '以上为建议项，无需确认。完整说明：docs/story-sourcing.md；单独查看：startup-guide。'))
