"""Reproducible two-minute synthetic acceptance fixture, never a historical production."""
import argparse
import math
import struct
import sys
import wave
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from history_workflow.core import Episode, initialize, new_episode, ROLES, SCORES, write


def run(root):
    initialize(root)
    name = new_episode(root, '合成测试非历史内容', 120, 180)['episode']
    e = Episode(root, name)
    text = '这是用于软件验证的合成材料。' * 24  # 312 characters, 120 seconds at 156/min
    e.content('source', {'id':'SRC001','title':'程序生成的合成测试材料','genre':'合成测试','locator':'测试段落','excerpt':text,'access':'USER_PROVIDED','obtained_at':'2026-10-28'})
    e.content('claim', {'id':'C001','text':'只验证数据链路，不构成历史事实','sources':['SRC001'],'reliability':'LIMITED','allowed_expression':'合成软件测试','reason':'已明确标注合成','paragraphs':['P001']})
    e.content('outline', '合成测试：仅验证状态、文本包、文件映射、时长和交接文档。')
    e.content('script', {'author':'synthetic_writer','text':text})
    from history_workflow.core import effective
    e.timing({'rate':effective(text)/2,'audio_tolerance':0.05})
    examples = root/'测试输入'
    examples.mkdir(exist_ok=True)
    for role in ROLES:
        r={'role':role,'input_hash':e.signature(),'reviewer':'synthetic_reviewer','evidence':'程序测试记录；未执行真实历史内容审核','conclusion':'PASS','issues':[], 'scores':{k:{'score':v,'reason':'合成断言'} for k,v in SCORES.items()},'checks':{k:True for k in ('time','identity','knowledge','causality','transition','repetition','promise')}}
        write(examples/f'review_{role}.json',r)
        e.review(r)
    e.lock()
    e.audio_package({'voice':'合成测试 非用户音色','settings':{'synthetic':True},'limit':1000})
    source=root/'测试输入/合成信号.wav'
    with wave.open(str(source),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000)
        chunk=b''.join(struct.pack('<h',int(1200*math.sin(2*math.pi*220*i/8000))) for i in range(8000))
        for _ in range(120):w.writeframes(chunk)
    from PIL import Image
    picture=root/'测试输入/合成灰色画面.png'
    Image.new('RGB',(1920,1080),'#4b5563').save(picture)
    for kind, aid, file in [('audio','A001',source),('image','IMG001',picture),('cover','COVER001',picture)]:
        d={'kind':kind,'id':aid,'file':str(file),'confirmed_mapping':True,'source':'程序合成测试','rights':'仅用于软件验证','scene':'单一灰色测试场景','paragraphs':['P001']}
        write(examples/f'asset_{aid}.json',d);e.asset(d)
        checks={'audio':['no_omission','no_repeat','no_truncation','voice_preserved'],'image':['identity','era','safe_motion','subtitle_space'],'cover':['consistency','readability','identity','rights']}[kind]
        d={'id':aid,'sha256':e.s['assets'][aid]['sha256'],'reviewer':'synthetic fixture','evidence':'纯合成断言，不代表真实视听审核','checks':{k:True for k in checks}}
        write(examples/f'verify_{aid}.json',d);e.verify_asset(d)
    plan={'responsible':'合成测试','shots':[{'id':'K001','image':'IMG001','paragraphs':['P001'],'start':0,'end':120,'time_basis':'AUDIO_VERIFIED','anchor_evidence':'合成WAV完整120秒，无逐字对齐','motion':'slow_push','purpose':'验证单图与长旁白映射','check_method':'测试数据结构，尚未在外部工具执行','start_crop':[0,0,1,1],'end_crop':[.01,.01,.98,.98],'safety_review':'合成数据，仅测试校验路径'}],'transitions':[]}
    write(examples/'plan.json',plan);e.set_plan(plan)
    result=e.document('TIMED')
    write(root/'合成测试说明.txt','这是120秒合成软件测试。审核为程序断言，音频是正弦信号，画面为纯色。不是历史节目，不是用户音色，没有验证任何剪辑软件能力。真实工具核验尚未完成，交接冻结应被阻断。')
    print(e.path)
    print(e.path/result['files'][0]['path'])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);run(p.parse_args().root.resolve())
