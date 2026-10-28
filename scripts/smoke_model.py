"""Real-model smoke test; small target before full audition. Not a synthetic test."""
import sys,time,resource,traceback
from pathlib import Path
import soundfile as sf
from history_tts.core import config,save_json
from history_tts.backend import Engine
from history_tts.audio import check_audio
from history_tts.pipeline import VOICES

c=config('configs/default.json')
c['runtime']['dtype']='float16'
c['generation']['max_new_tokens']=256
out=Path('runs/model-smoke'); out.mkdir(parents=True,exist_ok=True)
result={'status':'running','config':c,'text':'公元二百零八年，曹操率军南下。'}
started=time.monotonic()
try:
    e=Engine(c,'design')
    result['load_seconds']=e.load_seconds
    print('Loaded:',e.provenance,flush=True)
    t=time.monotonic()
    wavs,sr=e.design(result['text'],VOICES['steady'],c['seed'])
    result['generation_seconds']=time.monotonic()-t
    sf.write(out/'smoke.wav',wavs[0],sr,subtype='PCM_16')
    result['quality']=check_audio(out/'smoke.wav')
    result['rtf']=result['generation_seconds']/result['quality']['duration']
    result['status']='complete'
except BaseException as ex:
    result.update(status='failed',error=repr(ex),traceback=traceback.format_exc())
    raise
finally:
    result['elapsed_seconds']=time.monotonic()-started
    result['peak_rss_bytes']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    save_json('reports/model-smoke.json',result)
    print(result,flush=True)
