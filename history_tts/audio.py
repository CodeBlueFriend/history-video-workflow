from pathlib import Path
import json
import os
import subprocess
import numpy as np
import soundfile as sf

def check_audio(path):
    data, sr = sf.read(path, dtype='float32', always_2d=True)
    if not len(data) or not np.isfinite(data).all():
        raise ValueError(f'空音频或非有限数值: {path}')
    mono = data.mean(axis=1)
    peak = float(np.max(np.abs(data)))
    if peak < 1e-5:
        raise ValueError(f'全静音: {path}')
    frame = max(1, int(sr * 0.02))
    rms = np.array([np.sqrt(np.mean(x*x)) for x in np.array_split(mono[:len(mono)//frame*frame], max(1,len(mono)//frame))])
    silent = rms < 0.00316  # -50 dBFS, 20 ms windows
    longest = current = 0
    for v in silent:
        current = current+1 if v else 0
        longest = max(longest, current)
    warnings = []
    if float(silent.mean()) > .65 or longest*.02 > 3:
        warnings.append('异常静音比例或连续静音，请试听')
    if peak >= .999:
        warnings.append('峰值接近削波，请试听')
    return {'sample_rate':sr, 'channels':data.shape[1], 'frames':len(data), 'duration':len(data)/sr,
            'peak':peak, 'silent_fraction':float(silent.mean()), 'longest_silence_seconds':longest*.02, 'warnings':warnings}

def normalize(source, target, c):
    """Two pass EBU R128, preserve pitch and duration; final PCM mono."""
    base = ['ffmpeg','-nostdin','-hide_banner','-y','-i',str(source)]
    filt = f"loudnorm=I={c['target_lufs']}:TP={c['true_peak_db']}:LRA=7"
    first = subprocess.run(base+['-af',filt+':print_format=json','-f','null','-'],capture_output=True,text=True,check=True)
    measure = json.loads(first.stderr[first.stderr.rfind('{'):first.stderr.rfind('}')+1])
    if not all(np.isfinite(float(measure[k])) for k in ('input_i','input_tp','input_lra','input_thresh','target_offset')):
        raise ValueError('响度无法测量，音频可能为空或静音')
    second = filt+f":measured_I={measure['input_i']}:measured_TP={measure['input_tp']}:measured_LRA={measure['input_lra']}:measured_thresh={measure['input_thresh']}:offset={measure['target_offset']}:linear=true:print_format=json"
    tmp = Path(target).with_suffix('.tmp.wav')
    result = subprocess.run(base+['-af',second,'-ar',str(c['sample_rate']),'-ac','1','-c:a','pcm_s16le',str(tmp)],capture_output=True,text=True,check=True)
    output = json.loads(result.stderr[result.stderr.rfind('{'):result.stderr.rfind('}')+1])
    info = check_audio(tmp)
    info['loudness'] = output
    os.replace(tmp,target)
    return info

def concatenate(rows, root, c):
    target = Path(root)/'narration.wav'
    tmp = target.with_suffix('.tmp.wav')
    sr = c['sample_rate']
    silence = np.zeros(round(c['pause_seconds']*sr),dtype=np.float32)
    cursor = 0
    with sf.SoundFile(tmp,'w',samplerate=sr,channels=1,subtype='PCM_16') as out:
        for i,row in enumerate(rows):
            wav, actual_sr = sf.read(Path(root)/row['audio'],dtype='float32')
            if actual_sr != sr or wav.ndim != 1:
                raise ValueError('分段音频格式不一致')
            row['start_sample'] = cursor
            row['start'] = cursor/sr
            out.write(wav)
            cursor += len(wav)
            row['end_sample'] = cursor
            row['end'] = cursor/sr
            row['duration'] = len(wav)/sr
            if i < len(rows)-1:
                out.write(silence)
                cursor += len(silence)
    os.replace(tmp,target)
    return {'audio':'narration.wav','frames':cursor,'duration':cursor/sr,'sample_rate':sr,'channels':1,'subtype':'PCM_16'}
