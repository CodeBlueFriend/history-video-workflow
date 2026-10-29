import argparse
import json
import sys
import subprocess
from pathlib import Path
from .core import Episode, WorkflowError, default_root, desktop, exclusive, initialize, new_episode, read, validate_caps, write
from .guidance import startup_guide, startup_text


def parser():
    p = argparse.ArgumentParser(description='历史长视频 V5 本地工作台；外部创作、审核与剪辑采用显式文件交接',
                                epilog=startup_text(), formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--root', type=Path, help='项目运行目录；默认当前程序工作区下 production')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('startup-guide', help='单独阅读素材检索、故事筛选与选题建议；无需初始化')
    init = sub.add_parser('init', help='在工作区初始化项目；桌面仅输出生产资料')
    init.add_argument('--output-dir', type=Path, help='生产资料输出目录，默认实际桌面/历史故事长篇')
    sub.add_parser('list', help='列出本集状态')
    sub.add_parser('story-history', help='查看已立项及补录的故事线历史；允许人物重复')
    for name in ('story-record', 'story-check'):
        q = sub.add_parser(name, help='补录已有故事历史' if name == 'story-record' else '检查故事线是否重复')
        q.add_argument('file', type=Path)
    q = sub.add_parser('story-profile', help='为旧项目补录或修改故事线档案')
    q.add_argument('episode'); q.add_argument('file', type=Path); q.add_argument('--reopen-reason')
    q = sub.add_parser('topic-options', help='导入2—10个候选选题，等待用户选择')
    q.add_argument('file', type=Path)
    q = sub.add_parser('topic-list', help='查看指定批次候选选题')
    q.add_argument('batch')
    q = sub.add_parser('topic-select', help='选择候选立项；省略候选编号时交互选择并补充想法')
    q.add_argument('batch'); q.add_argument('candidate', nargs='?'); q.add_argument('--idea', default='')
    q.add_argument('--minimum', type=float, default=1800); q.add_argument('--maximum', type=float, default=1860)
    q.add_argument('--sample', action='store_true', help='样片/测试项目，不计故事历史或占用')
    q = sub.add_parser('idea', help='从UTF-8文本追加个人想法，失效旧审核与下游产物')
    q.add_argument('episode'); q.add_argument('file', type=Path); q.add_argument('--reopen-reason')

    n = sub.add_parser('new', help='复制模板创建新集')
    n.add_argument('title'); n.add_argument('--minimum', type=float, default=1800); n.add_argument('--maximum', type=float, default=1860)
    n.add_argument('--story-file', required=True, type=Path, help='故事线JSON档案，用于重复检查')
    n.add_argument('--sample', action='store_true', help='样片/测试项目，不计故事历史或占用')
    for name in ('capabilities', 'topic', 'public-source'):
        q = sub.add_parser(name); q.add_argument('file', type=Path)
    for name in ('status', 'check', 'lock', 'handoff', 'deliver', 'preflight', 'run-start', 'cover-status', 'publication-check'):
        q = sub.add_parser(name); q.add_argument('episode')
    q = sub.add_parser('cover-plan', help='查看本集封面快照；--refresh显式采用当前默认规格并保留历史')
    q.add_argument('episode'); q.add_argument('--refresh', action='store_true')
    q = sub.add_parser('publication-package', help='生成各平台本地发布文案包；标题与视频一致，不执行发布')
    q.add_argument('episode'); q.add_argument('--file', type=Path, help='导入编辑后的文案JSON；省略时复用文案或建立待填写草稿')
    q = sub.add_parser('run-finish', help='总结本次制作耗时和有回执的实际算力用量；排除手动配音')
    q.add_argument('episode'); q.add_argument('file', type=Path)
    q = sub.add_parser('content', help='导入资料、提纲或文稿；不自动生成历史事实')
    q.add_argument('episode'); q.add_argument('kind', choices=['source','claim','timeline','disputes','outline','script']); q.add_argument('file', type=Path); q.add_argument('--reopen-reason')
    q = sub.add_parser('stage-packet', help='写稿前的资料/提纲独立审核包')
    q.add_argument('episode'); q.add_argument('role', choices=['evidence','outline'])
    q = sub.add_parser('stage-review', help='导入真实前置审核记录')
    q.add_argument('episode'); q.add_argument('file', type=Path)
    q = sub.add_parser('review-packet', help='只提供事实、目标稿与量表的独立审核输入')
    q.add_argument('episode'); q.add_argument('role')
    for name in ('review','resolve','timing','audio-package','receive-audio','asset','verify-asset','plan','export','accept'):
        q = sub.add_parser(name); q.add_argument('episode'); q.add_argument('file', type=Path)
    q = sub.add_parser('document'); q.add_argument('episode'); q.add_argument('stage', choices=['PLAN','TIMED'])
    return p


def main(argv=None):
    command_parser = parser()
    if not (argv if argv is not None else sys.argv[1:]):
        command_parser.print_help()
        return 0
    args = command_parser.parse_args(argv)
    try:
        root = args.root.expanduser().resolve() if args.root else default_root()
        cmd = args.command
        if cmd != 'startup-guide':
            print(startup_text(), file=sys.stderr)
        if cmd == 'startup-guide':
            result = startup_guide()
        elif cmd == 'init':
            result = initialize(root, args.output_dir or desktop() / '历史故事长篇')
        elif cmd in ('story-history', 'story-record', 'story-check'):
            from .story_history import history, record, check
            result = history(root) if cmd == 'story-history' else (record(root, read(args.file)) if cmd == 'story-record' else check(root, read(args.file)))
        elif cmd in ('topic-options', 'topic-list', 'topic-select'):
            from .topics import save_options, batch_path, select
            from .core import require
            if cmd == 'topic-options':
                result = save_options(root, read(args.file))
            elif cmd == 'topic-list':
                result = read(batch_path(root, args.batch))
                from .story_history import check
                result['storyline_checks'] = {o['id']: check(root, o['story']) if o.get('story') else {'status': 'MISSING_PROFILE'} for o in result['options']}
            else:
                if args.candidate is None:
                    require(sys.stdin.isatty(), '非交互调用请提供候选编号；先用 topic-list 查看选项')
                    data = read(batch_path(root, args.batch))
                    for option in data['options']:
                        print(f"{option['id']}: {option['title']}\n  {option['summary']}\n  角度：{option['angle']}", file=sys.stderr)
                    args.candidate = input('请输入候选编号：').strip()
                    extra = input('补充你的想法（可留空，后续可用 idea 追加）：').strip()
                    args.idea = '\n'.join(x for x in (args.idea, extra) if x)
                result = select(root, args.batch, args.candidate, args.idea, args.minimum, args.maximum,
                                production_kind='SAMPLE' if args.sample else None)
        elif cmd == 'new':
            result = new_episode(root, args.title, args.minimum, args.maximum, story=read(args.story_file),
                                 production_kind='SAMPLE' if args.sample else 'FORMAL')
        elif cmd == 'list':
            result = [read(p) for p in root.glob('EP*/00_项目记录/工作台状态.json')]
            result = [{k:s[k] for k in ('episode','status','revision')} for s in result]
        elif cmd in ('capabilities','topic','public-source'):
            data = read(args.file)
            with exclusive(root):
                if cmd == 'capabilities':
                    validate_caps(data)
                    path = root / '00_项目配置/已核验工具.json'
                    if path.exists():
                        from .core import digest
                        write(root / f'00_项目配置/工具历史/{digest(read(path))}.json', read(path))
                    write(path, data)
                else:
                    from .core import require
                    require(data.get('id') and data.get('title'), '记录需要 id 和 title')
                    path = root / ('01_选题库/工作台选题库.json' if cmd=='topic' else '02_公共素材库/工作台来源索引.json')
                    items = read(path) if path.exists() else []
                    items.append(data); write(path, items)
                result = {'saved': str(path)}
        else:
            with exclusive(root):
                episode = Episode(root, args.episode)
                from .budget import save_preflight, start_run, finish_run
                if episode.s.get('script') and cmd not in ('status', 'check', 'preflight', 'run-start', 'run-finish', 'story-profile', 'cover-plan'):
                    preview = save_preflight(episode)
                    print(json.dumps({'startup_preflight': preview}, ensure_ascii=False), file=sys.stderr)
                if cmd == 'preflight':
                    result = save_preflight(episode)
                elif cmd == 'run-start':
                    result = start_run(episode)
                elif cmd == 'run-finish':
                    result = finish_run(episode, read(args.file))
                elif cmd == 'status':
                    result = episode.s
                elif cmd == 'cover-plan':
                    from .covers import config as cover_config, refresh_plan
                    result = refresh_plan(episode) if args.refresh else episode.s.get('cover_plan') or cover_config(root)
                elif cmd == 'cover-status':
                    from .covers import delivery_status
                    result = delivery_status(episode.s)
                elif cmd == 'publication-package':
                    from .publishing import save_package
                    result = save_package(episode, read(args.file) if args.file else None)
                elif cmd == 'publication-check':
                    from .publishing import check_package
                    result = check_package(episode)
                elif cmd == 'check':
                    result = {'lock_blockers': episode.blockers(), 'status': episode.s['status'], 'integrations': read(root/'00_项目配置/工作台配置.json')['integrations']}
                elif cmd == 'story-profile':
                    from .story_history import set_profile
                    result = set_profile(episode, read(args.file), args.reopen_reason)
                elif cmd == 'idea':
                    from .topics import add_idea
                    result = add_idea(episode, args.file.read_text(encoding='utf-8'), args.reopen_reason)
                elif cmd == 'content':
                    data = args.file.read_text(encoding='utf-8') if args.kind=='outline' else read(args.file)
                    result = episode.content(args.kind, data, args.reopen_reason)
                    if args.kind == 'script':
                        try:
                            result['preflight'] = save_preflight(episode)
                        except WorkflowError as error:
                            result['preflight_pending'] = str(error)
                elif cmd == 'stage-packet':
                    result = episode.stage_packet(args.role)
                elif cmd == 'stage-review':
                    result = episode.stage_review(read(args.file))
                elif cmd == 'review-packet':
                    result = episode.review_packet(args.role)
                elif cmd == 'document':
                    result = episode.document(args.stage)
                elif cmd in ('lock','handoff','deliver'):
                    result = getattr(episode, cmd)()
                else:
                    method = {'verify-asset':'verify_asset','audio-package':'audio_package','receive-audio':'receive_audio','plan':'set_plan','export':'register_export'}.get(cmd, cmd)
                    result = getattr(episode, method)(read(args.file))
                if cmd in ('lock', 'audio-package', 'receive-audio', 'asset', 'verify-asset', 'document', 'handoff', 'export', 'accept') and read(root/'00_项目配置/工作台配置.json').get('output_dir'):
                    try:
                        result['delivery'] = episode.deliver()
                    except (WorkflowError, OSError) as error:
                        result['delivery_error'] = str(error)
                        result['recovery'] = '工作区操作已保存；排除输出问题后运行 deliver 重试'
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (WorkflowError, OSError, ValueError, KeyError, TypeError, ImportError, subprocess.CalledProcessError, EOFError) as e:
        print(json.dumps({'error': str(e), 'status': 'BLOCKED'}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
