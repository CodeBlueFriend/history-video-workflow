"""Verify official ModelScope files against pinned Hugging Face commit; set local path only on success."""
import hashlib
import json
import sys
from pathlib import Path
from huggingface_hub import HfApi
from history_tts.core import read_json, save_json, file_hash

kind = sys.argv[1]
folder = Path(sys.argv[2]).expanduser().resolve()
p = Path('configs/default.json')
c = read_json(p)
spec = c['models'][kind]
info = HfApi().model_info(spec['repo'],revision=spec['revision'],files_metadata=True)
result = {'kind':kind,'repo':spec['repo'],'revision':info.sha,'local_path':str(folder),'files':[]}
for f in info.siblings:
    if not f.rfilename.endswith(('.json','.safetensors','.txt','.model','.tiktoken')):
        continue
    target=folder/f.rfilename
    if f.lfs:
        actual=file_hash(target); expected=f.lfs.sha256
    else:
        data=target.read_bytes()
        actual=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        expected=f.blob_id
    if actual != expected:
        raise RuntimeError(f'Hash mismatch: {f.rfilename} {actual} != {expected}')
    result['files'].append({'path':f.rfilename,'hash':actual,'verified':True})
save_json(f'reports/model-{kind}-verification.json',result)
spec['path']=str(folder)
save_json(p,c)
print(f'{kind}: {len(result["files"])} files verified against {info.sha}',flush=True)
