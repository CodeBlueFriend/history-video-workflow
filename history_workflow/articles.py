"""Versioned Toutiao reading editions derived from the locked story, without posting."""
import copy
import html
import uuid
from .core import digest, file_hash, inside, now, read, require, write
from .publishing import video_title

DEFAULTS = {
    'version':1, 'enabled':True, 'trigger':'FINAL_ACCEPTED',
    'title_policy':'文章完整标题与视频一致；简介吸引句和分节标题单列。',
    'adaptation_policy':'从锁稿改写为完整阅读文章；先铺垫背景，保留人物关系、因果和必要的不确定性。去掉口播提示、听觉重复及镜头指令，短段落配小标题，不逐字搬运字幕。',
    'layout':{'font_size_px':18,'line_height':1.9,'max_width_px':760},
    'formats':['markdown','html','json'],
    'upload':{'mode':'MANUAL','automatic_enabled':False,'adapter':None},
    'delivery':'与封面及视频发布资料集中到08_发布包，文章正文单列专项文件夹。',
}


def config(root):
    p=root/'00_项目配置/今日头条文字版配置.json'
    c=read(p) if p.exists() else copy.deepcopy(DEFAULTS)
    require(c.get('trigger')=='FINAL_ACCEPTED', '文字版自动任务须在视频验收后触发')
    require(c.get('upload',{}).get('automatic_enabled') is False, '当前只实现本地交付，自动上传适配器尚未实现')
    layout=c['layout']
    require(12 <= layout['font_size_px'] <= 28 and 1.3 <= layout['line_height'] <= 2.5 and 360 <= layout['max_width_px'] <= 1200, '文章排版参数超出范围')
    return c


def basis(episode):
    return digest({'script':episode.s.get('script'),'publication':episode.s.get('publication'),
                   'sources':episode.s.get('sources',{})})


def packet(episode):
    episode.require_locked()
    return {'schema':1,'platform':'TOUTIAO','title':video_title(episode.s),'basis_hash':basis(episode),
            'script':episode.s['script'],'sources':episode.s.get('sources',{}),'settings':config(episode.root),
            'instruction':'由创作助手阅读此包后专门改写文章并审核，再用article-package --file导入；此包不是文章成稿。'}


def ensure_task(episode):
    content=episode.s.get('toutiao_article_content')
    bound=content and content.get('basis_hash')==basis(episode)
    task={'basis_hash':basis(episode),'status':'ADAPTATION_READY' if bound else 'NEEDS_ADAPTATION',
          'video_accepted':episode.s.get('status')=='FINAL_ACCEPTED' and bool(episode.s.get('accepted')),
          'title':video_title(episode.s),'time':now()}
    write(episode.path/'08_发布包/今日头条文字版任务/改写任务.json',packet(episode))
    episode.s['toutiao_article_task']=task
    episode.save('建立今日头条文字版专项任务；未执行上传')
    return task


def normalize(episode,data):
    require(isinstance(data,dict) and data.get('basis_hash')==basis(episode), '文章未绑定当前锁稿、来源及标题；请重新改写')
    require(data.get('title')==video_title(episode.s), '文章标题须与视频完整标题一致')
    require(isinstance(data.get('sections'),list) and data['sections'], '文章须包含阅读分节')
    result={'title':data['title'],'basis_hash':data['basis_hash'],'subtitle':data.get('subtitle',''),
            'lead':data.get('lead',[]),'sections':data['sections'],'content_note':data.get('content_note',''),
            'source_ids':data.get('source_ids',[]),'tags':data.get('tags',[]),'review':data.get('review',{})}
    require(isinstance(result['subtitle'],str) and isinstance(result['content_note'],str) and result['content_note'].strip(), '缺少文字版内容说明')
    require(isinstance(result['lead'],list) and result['lead'], '缺少故事背景导语')
    paragraphs=list(result['lead'])
    for section in result['sections']:
        require(isinstance(section,dict) and isinstance(section.get('heading'),str) and section['heading'].strip(), '缺少分节标题')
        require(isinstance(section.get('paragraphs'),list) and section['paragraphs'], '缺少分节正文')
        paragraphs+=section['paragraphs']
    require(all(isinstance(p,str) and p.strip() for p in paragraphs), '正文段落必须是非空文本')
    require(isinstance(result['source_ids'],list) and result['source_ids'] and all(s in episode.s.get('sources',{}) for s in result['source_ids']), '文章引用来源编号不存在')
    require(isinstance(result['tags'],list) and all(isinstance(t,str) and t.strip() and not any(c.isspace() or c=='#' for c in t) for t in result['tags']), '文章标签格式无效')
    review=result['review']
    require(isinstance(review,dict) and review.get('reviewer') and review.get('evidence') and
            all(review.get('checks',{}).get(k) is True for k in ('faithful','readable','uncertainty_preserved','humanizer')), '缺少实际文章审核和Humanizer检查')
    return result


def markdown(episode,content):
    lines=['# '+content['title'],'']
    if content['subtitle']:lines += [content['subtitle'],'']
    for p in content['lead']:lines += [p,'']
    for section in content['sections']:
        lines += ['## '+section['heading'],'']
        for p in section['paragraphs']:lines += [p,'']
    lines += ['---','','内容说明：'+content['content_note'],'','参考资料：']
    for sid in content['source_ids']:
        source=episode.s['sources'][sid]
        lines.append('- '+source['title'])
    return '\n'.join(lines)+'\n'


def body_html(episode,content):
    esc=html.escape
    paragraphs=lambda ps: ''.join('<p>'+esc(p)+'</p>' for p in ps)
    body=('<p style="color:#555">'+esc(content['subtitle'])+'</p>') if content['subtitle'] else ''
    body+=paragraphs(content['lead'])
    for section in content['sections']:
        body+='<h2>'+esc(section['heading'])+'</h2>'+paragraphs(section['paragraphs'])
    body+='<hr><p>内容说明：'+esc(content['content_note'])+'</p><p>参考资料：</p><ul>'
    for sid in content['source_ids']:body+='<li>'+esc(episode.s['sources'][sid]['title'])+'</li>'
    return body+'</ul>'


def html_document(episode,content,settings):
    title=html.escape(content['title']);layout=settings['layout'];body=body_html(episode,content)
    parts=content['title'].split('：',1)
    heading=html.escape(parts[0])+'：<br>'+html.escape(parts[1]) if len(parts)==2 else title
    # Copying the body excludes title, tags and local workflow status. No network requests.
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>body{{margin:0;background:#f4f2ed;color:#242424;font-family:"PingFang SC","Microsoft YaHei",sans-serif}}main{{max-width:{layout['max_width_px']}px;margin:28px auto;background:white;padding:36px;box-sizing:border-box}}h1{{font-size:30px;line-height:1.5;text-wrap:balance}}h2{{font-size:23px;margin:2em 0 1em}}#body{{font-size:{layout['font_size_px']}px;line-height:{layout['line_height']}}}p{{margin:0 0 1.25em}}nav{{max-width:{layout['max_width_px']}px;margin:20px auto;line-height:1.7;padding:0 16px;box-sizing:border-box}}button{{padding:9px 16px;margin-right:12px;cursor:pointer}}@media(max-width:600px){{main{{margin:0;padding:24px 20px}}h1{{font-size:26px}}}}@media print{{nav{{display:none}}body{{background:white}}main{{margin:0;padding:0}}}}</style>
<nav><button onclick="copyTitle()">复制标题</button><button onclick="copyBody()">复制排版正文</button><span id="notice" role="status">本地文章预览：分别粘贴标题和正文，上传后复核排版。</span></nav>
<main><h1 id="title">{heading}</h1><article id="body">{body}</article></main>
<script>async function copyNode(id,rich){{const n=document.getElementById(id);const text=rich?n.innerText:n.textContent;try{{if(rich&&navigator.clipboard&&window.ClipboardItem){{await navigator.clipboard.write([new ClipboardItem({{'text/html':new Blob([n.innerHTML],{{type:'text/html'}}),'text/plain':new Blob([text],{{type:'text/plain'}})}})])}}else if(navigator.clipboard){{await navigator.clipboard.writeText(text)}}else{{throw new Error('fallback')}}document.getElementById('notice').textContent='已复制，请到发布页粘贴并预览。'}}catch(e){{const r=document.createRange();r.selectNodeContents(n);const s=window.getSelection();s.removeAllRanges();s.addRange(r);const ok=document.execCommand('copy');document.getElementById('notice').textContent=ok?'已复制，请到发布页粘贴并预览。':'已选中文本，请按⌘C或Ctrl+C复制。';}}}}function copyTitle(){{copyNode('title',false)}}function copyBody(){{copyNode('body',true)}}</script></html>'''


def build(episode,data=None):
    episode.require_locked()
    content=normalize(episode,data if data is not None else episode.s.get('toutiao_article_content'))
    settings=config(episode.root)
    accepted=episode.s.get('status')=='FINAL_ACCEPTED' and bool(episode.s.get('accepted'))
    return {'schema':1,'platform':'TOUTIAO','content':content,'settings':settings,
            'status':'READY_FOR_MANUAL_UPLOAD' if accepted else 'ARTICLE_READY_VIDEO_REVIEW_PENDING',
            'video_accepted':accepted,'input_hash':digest({'basis':basis(episode),'content':content,'settings':settings,'video_accepted':accepted}),
            'upload':{'mode':'MANUAL','state':'NOT_UPLOADED','automatic_adapter':None},
            'article_html':body_html(episode,content)}


def save_article(episode,data=None):
    if data is None and not episode.s.get('toutiao_article_content'):return ensure_task(episode)
    bundle=build(episode,data);content=bundle['content']
    version=len(episode.s.get('toutiao_article_packages',[]))+1
    folder=episode.path/f'08_发布包/今日头条文字版/历史版本/v{version:03d}_{uuid.uuid4().hex[:8]}'
    write(folder/'今日头条文字版.md',markdown(episode,content))
    write(folder/'今日头条文字版.html',html_document(episode,content,bundle['settings']))
    write(folder/'文章数据.json',bundle)
    record={'version':version,'time':now(),'directory':str(folder.relative_to(episode.path)), 'input_hash':bundle['input_hash'],'status':bundle['status'],
            'files':[{'path':str(p.relative_to(episode.path)),'sha256':file_hash(p)} for p in sorted(folder.iterdir())]}
    episode.s['toutiao_article_content']=content
    episode.s.setdefault('toutiao_article_packages',[]).append(record)
    episode.s['toutiao_article_task']={'basis_hash':basis(episode),'status':'ADAPTATION_READY','video_accepted':bundle['video_accepted']}
    episode.save('生成今日头条文字版及排版预览；未上传')
    return record


def check_article(episode):
    records=episode.s.get('toutiao_article_packages',[]);require(records,'缺少今日头条文字版')
    current=build(episode);latest=records[-1]
    require(latest['input_hash']==current['input_hash'],'今日头条文字版已过期，请按当前锁稿、来源和标题重新生成')
    for item in latest['files']:
        path=inside(episode.path,item['path'])
        require(path.is_file() and file_hash(path)==item['sha256'],'今日头条文字版文件缺失或被修改')
    return latest


def after_completion(episode):
    if not config(episode.root)['enabled'] or episode.s.get('production_kind')=='SAMPLE':return {'status':'DISABLED'}
    task=ensure_task(episode)
    return save_article(episode) if task['status']=='ADAPTATION_READY' else task
