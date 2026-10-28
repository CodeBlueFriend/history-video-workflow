import json
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf
from history_tts.core import split_text, assign_ids, pronunciation, save_json, read_json, config
from history_tts.pipeline import run
from history_tts.audio import check_audio

class FakeEngine:
    """Only infrastructure tests; synthetic tones are NEVER presented as TTS evidence."""
    calls = []
    fails = 0
    load_seconds = 0
    def __init__(self,*args): pass
    def reference(self,*args): pass
    def clone(self,text,seed):
        self.calls.append(text)
        if self.fails:
            type(self).fails -= 1
            raise RuntimeError('injected failure')
        t=np.arange(24000*2)/24000
        return [(.15*np.sin(2*np.pi*200*t)).astype('float32')],24000

@pytest.fixture
def setup(tmp_path):
    c=config('configs/default.json')
    c['voices_dir']=str(tmp_path/'voices')
    c['pronunciation']=str(tmp_path/'pronunciation.json')
    save_json(c['pronunciation'],{'replacements':[{'from':'208','to':'二百零八'}]})
    folder=tmp_path/'voices'/'steady'; folder.mkdir(parents=True)
    sf.write(folder/'reference.wav',np.sin(np.arange(24000)*.02)*.1,24000)
    (folder/'reference.txt').write_text('测试参考',encoding='utf-8')
    save_json(folder/'voice.json',{'voice_id':'steady','status':'ready'})
    source=tmp_path/'source.txt'; source.write_text('公元208年。\n\n江东议事。\n\n赤壁往事。',encoding='utf-8')
    FakeEngine.calls=[]; FakeEngine.fails=0
    return c,source,tmp_path/'run'

def test_resume_regen_change_and_time(setup):
    c,src,out=setup
    a=run(c,src,out,'steady',engine_factory=FakeEngine,limit=1)
    assert a['status']=='paused' and len(FakeEngine.calls)==1
    b=run(c,src,out,'steady',engine_factory=FakeEngine)
    assert b['status']=='complete' and len(FakeEngine.calls)==3
    assert [r['id'] for r in b['segments']]==['p00001','p00002','p00003']
    assert b['segments'][1]['start_sample']==48000+10800
    assert b['mix']['frames']==3*48000+2*10800
    info=sf.info(out/'narration.wav'); assert info.frames==b['mix']['frames']
    run(c,src,out,'steady',engine_factory=FakeEngine)
    assert len(FakeEngine.calls)==3
    run(c,src,out,'steady',['p00002'],engine_factory=FakeEngine)
    assert len(FakeEngine.calls)==4
    src.write_text('新增一句。\n公元208年。\n\n江东议事。\n\n赤壁往事。',encoding='utf-8')
    d=run(c,src,out,'steady',engine_factory=FakeEngine)
    assert len(FakeEngine.calls)==5
    assert [r['id'] for r in d['segments']]==['p00004','p00001','p00002','p00003']
    c['pause_seconds']=1
    run(c,src,out,'steady',engine_factory=FakeEngine)
    assert len(FakeEngine.calls)==5
    (Path(c['voices_dir'])/'steady'/'reference.txt').write_text('参考改变',encoding='utf-8')
    run(c,src,out,'steady',engine_factory=FakeEngine)
    assert len(FakeEngine.calls)==9

def test_failure_retry_and_stale_mix(setup):
    c,src,out=setup
    run(c,src,out,'steady',engine_factory=FakeEngine)
    FakeEngine.fails=5
    with pytest.raises(RuntimeError):
        run(c,src,out,'steady',['p00002'],engine_factory=FakeEngine)
    assert not (out/'narration.wav').exists()
    m=read_json(out/'manifest.json')
    assert m['status']=='failed'
    assert m['segments'][1]['attempts_this_run']==3
    assert len(FakeEngine.calls)==6
    FakeEngine.fails=0
    m=run(c,src,out,'steady',engine_factory=FakeEngine)
    assert m['status']=='complete' and len(FakeEngine.calls)==7

def test_pronunciation_and_offsets():
    text='鲁肃来了！\n\n公元208年，江东议事。'
    rows=split_text(text,10)
    assert all(text[r['source_start']:r['source_end']]==r['original'] for r in rows)
    spoken,mapping=pronunciation('208年',{'replacements':[{'from':'208','to':'二百零八'}]})
    assert spoken=='二百零八年' and mapping[0]['source_end']==3
    old=[{'id':'p00001','original':'甲。'},{'id':'p00002','original':'甲。'}]
    assert [r['id'] for r in assign_ids([{'original':'甲。'},{'original':'甲。'}],old)]==['p00001','p00002']

def test_empty_silence(setup):
    c,src,out=setup
    with pytest.raises(ValueError):split_text(' \n ')
    sf.write(src.with_suffix('.wav'),np.zeros(24000),24000)
    with pytest.raises(ValueError):check_audio(src.with_suffix('.wav'))

def test_corrupt_cache_and_rules(setup):
    c,src,out=setup
    m=run(c,src,out,'steady',engine_factory=FakeEngine)
    (out/m['segments'][0]['audio']).write_bytes(b'bad')
    run(c,src,out,'steady',engine_factory=FakeEngine)
    assert len(FakeEngine.calls)==4
    save_json(c['pronunciation'],{'replacements':[{'from':'208','to':'二零八'}]})
    run(c,src,out,'steady',engine_factory=FakeEngine)
    assert len(FakeEngine.calls)==5
