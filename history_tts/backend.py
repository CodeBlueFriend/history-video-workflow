from __future__ import annotations
import gc
import importlib.metadata
import json
import platform
import shutil
import subprocess
import time
from pathlib import Path
from .core import save_json, read_json


def environment():
    import psutil
    import torch
    info = {'os':platform.platform(), 'machine':platform.machine(), 'python':platform.python_version(),
            'memory_total_gib':psutil.virtual_memory().total/2**30,'memory_available_gib':psutil.virtual_memory().available/2**30,
            'disk_free_gib':shutil.disk_usage('.').free/2**30,'torch':torch.__version__,
            'cuda':torch.cuda.is_available(),'mps_built':torch.backends.mps.is_built(),'mps_available':torch.backends.mps.is_available(),
            'ffmpeg':shutil.which('ffmpeg'),'qwen_tts':importlib.metadata.version('qwen-tts')}
    if info['cuda']:
        info['gpu'] = torch.cuda.get_device_name(0)
        info['vram_gib'] = torch.cuda.get_device_properties(0).total_memory/2**30
    elif platform.system() == 'Darwin':
        info['gpu'] = subprocess.check_output(['system_profiler','SPDisplaysDataType'],text=True)
        info['vram_note'] = 'Apple Silicon 共享统一内存，无独立显存'
    return info


def runtime(c):
    import torch
    r = dict(c['runtime'])
    if r['device'] == 'auto':
        r['device'] = 'cuda:0' if torch.cuda.is_available() else ('mps' if torch.backends.mps.is_available() else 'cpu')
    if r['device'] == 'cpu' and r['dtype'] != 'float32':
        raise ValueError('CPU 请使用 float32')
    if r['device'] == 'mps' and r['dtype'] not in ('float32','float16'):
        raise ValueError('本项目 MPS 仅允许 float32/float16；必须实测后选择')
    if r['attention'] not in ('eager','sdpa'):
        raise ValueError('当前工程只启用 eager 或 sdpa')
    return r


def model_path(c, kind, download=False):
    from huggingface_hub import snapshot_download
    spec = c['models'][kind]
    if spec.get('path'):
        p = Path(spec['path']).expanduser().resolve()
        if not p.is_dir():
            raise FileNotFoundError(p)
        if not spec.get('revision') or spec['revision'] == 'main':
            raise ValueError('本地模型也必须记录确定的版本号')
        return str(p)
    if len(spec['revision']) != 40:
        raise ValueError('请先运行 download，将 main 解析并固定为实际 commit')
    return snapshot_download(spec['repo'],revision=spec['revision'],cache_dir=c['model_cache'],local_files_only=not download,
                             allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.tiktoken'], max_workers=3)

class Engine:
    def __init__(self,c,kind):
        import torch
        from qwen_tts import Qwen3TTSModel
        self.c = c
        self.kind = kind
        self.runtime = runtime(c)
        torch.set_num_threads(self.runtime['threads'])
        start = time.monotonic()
        self.model = Qwen3TTSModel.from_pretrained(model_path(c,kind),device_map=self.runtime['device'],
                      dtype=getattr(torch,self.runtime['dtype']),attn_implementation=self.runtime['attention'])
        self.load_seconds = time.monotonic()-start
        self.prompt = None
        self.provenance = {'model':c['models'][kind], 'runtime':self.runtime,
            'qwen_tts':importlib.metadata.version('qwen-tts'),'torch':torch.__version__,
            'transformers':importlib.metadata.version('transformers')}

    def seed(self, value):
        from transformers import set_seed
        set_seed(value)

    def design(self,text,description,seed):
        self.seed(seed)
        return self.model.generate_voice_design(text=text,language='Chinese',instruct=description,
                         non_streaming_mode=True,**self.c['generation'])

    def reference(self, audio, text):
        # Rebuilt from portable audio/text at every process start, never pickle arbitrary objects.
        self.prompt = self.model.create_voice_clone_prompt(ref_audio=str(audio),ref_text=text,x_vector_only_mode=False)

    def clone(self,text,seed):
        self.seed(seed)
        return self.model.generate_voice_clone(text=text,language='Chinese',voice_clone_prompt=self.prompt,
                         non_streaming_mode=True,**self.c['generation'])
