from __future__ import annotations
import datetime
import importlib.metadata
import os
import time
from pathlib import Path
import soundfile as sf
from .core import digest, file_hash, save_json, read_json, split_text, assign_ids, pronunciation, lock
from .audio import check_audio, normalize, concatenate
from .backend import Engine, runtime

VOICES = {
 'steady': '成熟男性，普通话，中低音域，吐字清楚，叙述沉稳自然，句间留有呼吸，适合长时间收听的历史故事旁白。不要播音腔，不要刻意压低嗓音。',
 'warm': '自然亲切的成年男声，普通话，像面对面讲故事，有交流感，语调随内容自然变化，清晰温暖，不夸张，不表演式喊叫。',
 'weathered': '略带岁月感的成年男声，普通话，音色有少许沙哑，克制而有叙事张力，发音清晰，保持自然音域，避免刻意压低嗓音。'
}

def event(path, name, **data):
    import json
    with Path(path).open('a',encoding='utf-8') as f:
        f.write(json.dumps({'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'event':name,**data},ensure_ascii=False)+'\n')

def voice_path(c, voice):
    if voice not in VOICES and (not voice or any(ch not in 'abcdefghijklmnopqrstuvwxyz0123456789_-' for ch in voice)):
        raise ValueError('音色编号只允许小写字母、数字、下划线和连字符')
    return Path(c['voices_dir'])/voice

def design(c, text_path, names=None):
    root = Path(c['voices_dir'])
    with lock(root):
        original = Path(text_path).read_text(encoding='utf-8')
        text, mapping = pronunciation(original,read_json(c['pronunciation']))
        text = text.strip()
        if not text:
            raise ValueError('测试稿为空')
        engine = None
        for index,name in enumerate(VOICES):
            if names and name not in names:
                continue
            folder = voice_path(c,name)
            folder.mkdir(parents=True,exist_ok=True)
            expected = digest({'text':text,'description':VOICES[name],'model':c['models']['design'],
                               'runtime':runtime(c),'generation':c['generation'],'seed':c['seed']+index})
            meta_file = folder/'voice.json'
            if meta_file.exists():
                previous = read_json(meta_file)
                if previous.get('design_fingerprint') != expected:
                    raise ValueError(f'{name} 已存在且配置不同。请备份旧音色目录后使用新目录，防止覆盖长期参考。')
                if previous.get('status') == 'ready' and file_hash(folder/'reference.wav') == previous['reference_sha256']:
                    print(f'{name}: 已存在，复用参考',flush=True)
                    continue
            if engine is None:
                engine = Engine(c,'design')
            meta = {'schema':1,'voice_id':name,'description':VOICES[name], 'reference_text':text,
                    'original_text':original,'pronunciation_changes':mapping,'design_fingerprint':expected,
                    'provenance':engine.provenance,'clone_model':c['models']['base'], 'generation':c['generation'],
                    'seed':c['seed']+index,'status':'generating','human_listening':'pending',
                    'transcript_verification':'pending: 输入文本不等于已核对的实际转写；试听核对后执行 confirm-reference'}
            save_json(meta_file,meta)
            (folder/'reference.txt').write_text(text,encoding='utf-8')
            (folder/'original.txt').write_text(original,encoding='utf-8')
            started = time.monotonic()
            try:
                wavs,sr = engine.design(text,VOICES[name],c['seed']+index)
                sf.write(folder/'reference.tmp.wav',wavs[0],sr,subtype='PCM_16')
                quality = check_audio(folder/'reference.tmp.wav')
                os.replace(folder/'reference.tmp.wav',folder/'reference.wav')
                meta.update(status='ready',audio='reference.wav',reference_sha256=file_hash(folder/'reference.wav'),
                            quality=quality,elapsed_seconds=time.monotonic()-started)
                save_json(meta_file,meta)
                event(folder/'generation.jsonl','design_complete',**meta)
                print(f"{name}: {quality['duration']:.2f}秒音频，耗时{meta['elapsed_seconds']:.1f}秒",flush=True)
            except Exception as exc:
                meta.update(status='failed',error=str(exc),elapsed_seconds=time.monotonic()-started)
                save_json(meta_file,meta)
                event(folder/'generation.jsonl','design_failed',**meta)
                raise
        if not (root/'default.json').exists() and (root/'steady'/'reference.wav').exists():
            save_json(root/'default.json',{'voice_id':'steady','selection':'provisional'})

def load_voice(c, name=None):
    if not name:
        name = read_json(Path(c['voices_dir'])/'default.json')['voice_id']
    folder = voice_path(c,name)
    meta = read_json(folder/'voice.json')
    if meta['status'] != 'ready':
        raise ValueError('音色尚未生成成功')
    text = (folder/'reference.txt').read_text(encoding='utf-8').strip()
    if not text:
        raise ValueError('参考文本为空')
    return folder,meta,text

def run(c, source, output, voice=None, regenerate=(), engine_factory=Engine, limit=None):
    """Lazy model loading: fully cached reruns do not initialize model or hit network."""
    output = Path(output).resolve()
    with lock(output):
        started = time.monotonic()
        folder,vm,ref_text = load_voice(c,voice)
        original = Path(source).read_text(encoding='utf-8')
        source_hash = digest(original)
        snapshots = output/'sources'
        snapshots.mkdir(exist_ok=True)
        (snapshots/f'{source_hash}.txt').write_text(original,encoding='utf-8')
        (output/'original.txt').write_text(original,encoding='utf-8')
        old = read_json(output/'manifest.json') if (output/'manifest.json').exists() else {}
        rows = assign_ids(split_text(original,c['max_chars']),old.get('segments',[]))
        unknown = set(regenerate)-{r['id'] for r in rows}
        if unknown:
            raise ValueError(f'指定段号不存在: {sorted(unknown)}')
        rules = read_json(c['pronunciation'])
        generation_identity = {'version':1, 'voice_id':vm['voice_id'], 'reference_audio_sha256':file_hash(folder/'reference.wav'),
                              'reference_text':ref_text,'model':c['models']['base'],'generation':c['generation'],
                              'runtime':runtime(c),'seed':c['seed'],'qwen_tts':importlib.metadata.version('qwen-tts'),
                              'torch':importlib.metadata.version('torch'),'transformers':importlib.metadata.version('transformers'),
                              'audio':{k:c[k] for k in ('sample_rate','target_lufs','true_peak_db')}}
        previous = {r['id']:r for r in old.get('segments',[])}
        for order,row in enumerate(rows):
            row['spoken'],row['pronunciation_changes'] = pronunciation(row['original'],rules)
            row.update(order=order+1,voice_id=vm['voice_id'],status='pending',start=None,end=None)
            row['fingerprint'] = digest({'spoken':row['spoken'],'identity':generation_identity})
            row['audio'] = f"segments/{row['id']}-{row['fingerprint'][:16]}.wav"
            prior = previous.get(row['id'],{})
            path = output/row['audio']
            if row['id'] not in regenerate and prior.get('fingerprint') == row['fingerprint'] and prior.get('status') == 'complete' and path.exists():
                try:
                    if file_hash(path) == prior.get('audio_sha256'):
                        row.update(status='complete',quality=check_audio(path),audio_sha256=prior['audio_sha256'],cached=True)
                except (ValueError,RuntimeError):
                    pass
        manifest = {'schema':1,'source_path':str(Path(source).resolve()),'source_sha256':source_hash,
                    'voice_id':vm['voice_id'],'voice_reference':str(folder),'reference_transcript_verification':vm.get('transcript_verification'),
                    'generation_identity':generation_identity,'config':c,'segments':rows,'status':'running',
                    'alignment':{'status':'not_run','interface':'audio + original.txt + spoken.txt -> word/character timestamps',
                                 'word_timestamps':None,'segment_times':'measured audio only'},
                    'human_review':['漏读、重复、历史专名发音、音色一致性、衔接自然度均需试听']}
        (output/'segments').mkdir(exist_ok=True)
        (output/'raw').mkdir(exist_ok=True)
        (output/'spoken.txt').write_text('\n\n'.join(r['spoken'] for r in rows),encoding='utf-8')
        # Prevent a stale full mix being mistaken for this run's output after failure/interruption.
        (output/'narration.wav').unlink(missing_ok=True)
        save_json(output/'manifest.json',manifest)
        event(output/'generation.jsonl','run_started',source_sha256=source_hash,regenerate=list(regenerate))
        engine = None
        generated = 0
        try:
            for row in rows:
                if row['status'] == 'complete':
                    event(output/'generation.jsonl','cache_hit',id=row['id'])
                    continue
                if limit is not None and generated >= limit:
                    manifest['status'] = 'paused'
                    break
                begin = time.monotonic()
                for attempt in range(c['retries']+1):
                    row['attempts_this_run'] = attempt+1
                    row['status'] = 'running'
                    save_json(output/'manifest.json',manifest)
                    try:
                        if engine is None:
                            engine = engine_factory(c,'base')
                            engine.reference(folder/'reference.wav',ref_text)
                            manifest['model_load_seconds'] = engine.load_seconds
                        seed = c['seed'] + int(row['fingerprint'][:8],16) % 100000 + attempt
                        wavs,sr = engine.clone(row['spoken'],seed)
                        raw = output/'raw'/f"{row['id']}-{row['fingerprint'][:16]}.wav"
                        sf.write(raw,wavs[0],sr,subtype='FLOAT')
                        raw_quality = check_audio(raw)
                        quality = normalize(raw,output/row['audio'],c)
                        # Flag extreme speaking rates and near token-limit duration; no fake ASR validation.
                        cps = len(row['spoken']) / quality['duration']
                        if cps < 1 or cps > 10:
                            quality['warnings'].append('字数/时长异常，可能漏读或重复，需试听')
                        if raw_quality['duration'] >= c['generation']['max_new_tokens']/12.5*.97:
                            quality['warnings'].append('接近token上限，可能截断，需试听')
                        row.update(status='complete',quality=quality,raw_audio=str(raw.relative_to(output)),
                                   audio_sha256=file_hash(output/row['audio']),elapsed_seconds=time.monotonic()-begin,
                                   cached=False,seed=seed)
                        event(output/'generation.jsonl','segment_complete',id=row['id'],seconds=row['elapsed_seconds'],quality=quality)
                        break
                    except Exception as exc:
                        row.update(status='failed',error=f'{type(exc).__name__}: {exc}')
                        event(output/'generation.jsonl','segment_failed',id=row['id'],attempt=attempt+1,error=row['error'])
                        save_json(output/'manifest.json',manifest)
                        if attempt == c['retries']:
                            raise
                generated += 1
                save_json(output/'manifest.json',manifest)
            if all(r['status']=='complete' for r in rows):
                manifest['mix'] = concatenate(rows,output,c)
                manifest['status'] = 'complete'
            manifest['elapsed_seconds'] = time.monotonic()-started
        except BaseException as exc:
            manifest.update(status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',error=str(exc))
            raise
        finally:
            import resource
            manifest['elapsed_seconds'] = time.monotonic()-started
            manifest['peak_rss_raw'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            manifest['peak_rss_unit'] = 'bytes' if __import__('sys').platform=='darwin' else 'KiB'
            save_json(output/'manifest.json',manifest)
            event(output/'generation.jsonl','run_finished',status=manifest['status'],seconds=manifest['elapsed_seconds'])
        return manifest
