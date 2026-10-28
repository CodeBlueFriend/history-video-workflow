import argparse
import json
import sys
from pathlib import Path
from .core import config, read_json, save_json, lock
from .backend import environment, model_path
from .pipeline import design, run, load_voice, voice_path, VOICES


def main():
    p = argparse.ArgumentParser(description='Qwen3-TTS 本地中文历史旁白')
    p.add_argument('--config',default='configs/default.json')
    sub = p.add_subparsers(dest='command',required=True)
    d = sub.add_parser('doctor'); d.add_argument('--output')
    d = sub.add_parser('download'); d.add_argument('--kind',choices=['all','design','base'],default='all')
    d = sub.add_parser('design'); d.add_argument('--text',default='examples/voice_audition.txt'); d.add_argument('--only',choices=list(VOICES))
    d = sub.add_parser('set-default'); d.add_argument('voice')
    d = sub.add_parser('confirm-reference',help='人工逐字核对 reference.wav 与 reference.txt 后标记')
    d.add_argument('voice')
    d = sub.add_parser('speak'); d.add_argument('text'); d.add_argument('--output',required=True); d.add_argument('--voice'); d.add_argument('--regenerate',nargs='+',default=[]); d.add_argument('--limit',type=int,help='本轮最多新生成几段，用于可控暂停')
    d = sub.add_parser('regen'); d.add_argument('--output',required=True); d.add_argument('--segments',nargs='+',required=True)
    args = p.parse_args()
    try:
        if args.command == 'doctor':
            report = environment()
            if args.output:
                save_json(args.output,report)
            print(json.dumps(report,ensure_ascii=False,indent=2))
            return
        c = config(args.config)
        if args.command == 'download':
            from huggingface_hub import HfApi
            raw = read_json(args.config)
            for kind in (['design','base'] if args.kind=='all' else [args.kind]):
                spec = c['models'][kind]
                if not spec.get('path') and len(spec['revision']) != 40:
                    spec['revision'] = HfApi().model_info(spec['repo'],revision=spec['revision']).sha
                    raw['models'][kind] = spec
                    save_json(args.config,raw)
                print(kind,model_path(c,kind,download=True),flush=True)
        elif args.command == 'design':
            design(c,args.text,[args.only] if args.only else None)
        elif args.command == 'set-default':
            load_voice(c,args.voice)
            with lock(c['voices_dir']):
                save_json(Path(c['voices_dir'])/'default.json',{'voice_id':args.voice,'selection':'user'})
            print('默认音色:',args.voice)
        elif args.command == 'confirm-reference':
            with lock(c['voices_dir']):
                folder,meta,text = load_voice(c,args.voice)
                meta.update(reference_text=text,transcript_verification='human_confirmed',human_listening='confirmed')
                save_json(folder/'voice.json',meta)
        elif args.command == 'speak':
            if args.limit is not None and args.limit < 1:
                raise ValueError('--limit 必须大于零')
            result = run(c,args.text,args.output,args.voice,args.regenerate,limit=args.limit)
            print(json.dumps({'status':result['status'],'output':str(Path(args.output).resolve()),'elapsed_seconds':result['elapsed_seconds']},ensure_ascii=False))
        elif args.command == 'regen':
            old = read_json(Path(args.output)/'manifest.json')
            result = run(c,Path(args.output)/'original.txt',args.output,old['voice_id'],args.segments)
            print(result['status'])
    except Exception as exc:
        print(f'错误: {type(exc).__name__}: {exc}',file=sys.stderr)
        sys.exit(1)

if __name__=='__main__':
    main()
