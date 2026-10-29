"""Script-based preflight estimates; never infer production cost from audio length."""
from __future__ import annotations
import copy
import math
import time
import uuid
from .core import effective, require, read, write, now, digest

DEFAULTS = {
    'schema': 1,
    'duration': {'characters_per_minute': 180, 'rate_range': [160, 220], 'readings': {}, 'net_intro_outro_seconds': 4.5},
    'workload': {'body_images_per_video_minute': 1.5, 'minimum_body_images': 12, 'covers': 4,
                 'image_attempt_multiplier': 1.25, 'llm_input_tokens_per_character': 12,
                 'llm_output_tokens_per_character': 6},
    'workload_basis': '可调整的预算假设，不是服务商实际用量；包含创作、审核、返修的粗估，不代表模型tokenizer精确计数',
    'prices': {'currency': 'CNY', 'llm_input_per_million_tokens': None,
               'llm_output_per_million_tokens': None, 'per_image_attempt': None,
               'render_per_video_minute': None},
    'benchmarks': {'content_seconds_per_character': None, 'image_seconds_per_attempt': None,
                   'edit_seconds_per_video_minute': None, 'render_seconds_per_video_minute': None},
    'manual_tts': {'mode': 'USER_WEB_MANUAL', 'include_time': False, 'include_cost': False},
}


def config(root):
    path = root / '00_项目配置/制作预算配置.json'
    if not path.exists():
        write(path, DEFAULTS)
    return read(path)


def number(value, label, positive=False):
    require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
            and (value > 0 if positive else value >= 0), label + '必须是有限非负数' if not positive else label + '必须是有限正数')
    return value


def preflight(state, settings):
    script = state.get('script')
    require(script and script.get('text'), '请先导入口播稿，再按字数预估')
    d = settings['duration']; w = settings['workload']; p = settings['prices']; b = settings['benchmarks']
    n = effective(script['text'], d.get('readings'))
    require(n > 0, '口播稿没有可计数的中文内容')
    rate = number(d['characters_per_minute'], '计划语速', True)
    slow, fast = [number(v, '语速范围', True) for v in d['rate_range']]
    require(slow <= rate <= fast, '计划语速必须位于语速范围内')
    extra = number(d.get('net_intro_outro_seconds', 0), '片头片尾')
    seconds = n / rate * 60 + extra
    minute = seconds / 60
    for k, v in w.items(): number(v, k)
    planned_images = {shot['image'] for shot in (state.get('plan') or {}).get('shots', []) if shot.get('image')}
    density=(state.get('visual_policy') or {}).get('images',{})
    recommended=max(math.ceil(density.get('minimum',w['minimum_body_images'])), math.ceil(minute*density.get('per_video_minute',w['body_images_per_video_minute'])))
    critical_count=len((state.get('plan') or {}).get('critical_scenes',[]))
    recommended=max(recommended,critical_count)
    body=max(len(planned_images), recommended)
    covers = len(state['cover_plan']['targets']) if state.get('cover_plan', {}).get('targets') else math.ceil(w['covers'])
    require(w['image_attempt_multiplier'] >= 1, '图片尝试倍率不能小于1')
    attempts = math.ceil((body + covers) * w['image_attempt_multiplier'])
    units = {'llm_input_tokens': math.ceil(n * w['llm_input_tokens_per_character']),
             'llm_output_tokens': math.ceil(n * w['llm_output_tokens_per_character']),
             'body_images': body, 'covers': covers, 'image_attempts': attempts, 'render_video_minutes': minute}
    prices = [('llm_input_per_million_tokens', units['llm_input_tokens']/1e6),
              ('llm_output_per_million_tokens', units['llm_output_tokens']/1e6),
              ('per_image_attempt', attempts), ('render_per_video_minute', minute)]
    costs = {k: None if p.get(k) is None else number(p[k], k)*u for k,u in prices}
    factors = [('content_seconds_per_character', n), ('image_seconds_per_attempt', attempts),
               ('edit_seconds_per_video_minute', minute), ('render_seconds_per_video_minute', minute)]
    times = {k: None if b.get(k) is None else number(b[k], k)*u for k,u in factors}
    return {'schema': 1, 'created_at': now(), 'episode': state['episode'],
            'script_hash': digest(script['text']), 'config_hash': digest(settings),
            'basis': 'SCRIPT_CHARACTERS_ONLY', 'characters': n,
            'estimated_video_seconds': seconds,
            'estimated_video_seconds_range': [n/fast*60+extra,n/slow*60+extra],
            'duration_class': '短样片' if seconds<300 else ('中篇' if seconds<1200 else '长篇'),
            'duration_settings': copy.deepcopy(d), 'workload': units, 'image_count_basis': 'MAX_OF_PLAN_AND_SCRIPT_BUDGET', 'planned_body_images':len(planned_images), 'recommended_body_images':recommended, 'additional_body_images_needed':max(0,recommended-len(planned_images)), 'workload_basis': settings['workload_basis'],
            'production_seconds': sum(times.values()) if all(v is not None for v in times.values()) else None,
            'production_stage_seconds': times, 'time_basis': '配置的实测单位耗时按串行相加；未知项不按零计算；并行墙钟时间需另行实测',
            'currency': p['currency'], 'estimated_cost': sum(costs.values()) if all(v is not None for v in costs.values()) else None,
            'priced_subtotal': sum(v for v in costs.values() if v is not None), 'cost_items': costs,
            'missing_prices': [k for k,v in costs.items() if v is None],
            'manual_audio_generation': 'EXCLUDED', 'audio_duration_used': False,
            'scope': '从现有稿件起进行完整制作的预算，不是增量修订报价；未知计费不推断免费；现有锁稿/音频对齐状态不变'}


def save_preflight(episode):
    result = preflight(episode.s, config(episode.root))
    folder = episode.path / '00_项目记录/制作预算'
    write(folder / '最新启动预估.json', result)
    write(folder / f'启动预估_{uuid.uuid4().hex[:12]}.json', result)
    return result


def start_run(episode):
    folder = episode.path / '00_项目记录/制作预算'
    require(not (folder/'进行中.json').exists(), '已有进行中的制作记录，请先总结该次制作')
    report = save_preflight(episode)
    run = {'id': uuid.uuid4().hex, 'started_at': now(), 'start_epoch': time.time(), 'preflight': report}
    write(folder/'进行中.json', run)
    return run


def finish_run(episode, receipt):
    folder = episode.path / '00_项目记录/制作预算'
    path = folder/'进行中.json'
    require(path.exists(), '没有进行中的制作记录；不能伪造开始时间')
    run=read(path); elapsed=max(0,time.time()-run['start_epoch'])
    excluded=number(receipt.get('excluded_manual_audio_and_wait_seconds',0),'扣除的手动配音/等待时间')
    require(excluded<=elapsed,'扣除时间不能超过本次墙钟时间')
    usage=receipt.get('usage',{})
    for k in usage: require(k in ('input_tokens','output_tokens','image_attempts','render_minutes','local_compute_seconds'),'未知用量字段: '+k);number(usage[k],k)
    prices=config(episode.root)['prices']
    pairs=[('input_tokens','llm_input_per_million_tokens',1e6),('output_tokens','llm_output_per_million_tokens',1e6),('image_attempts','per_image_attempt',1),('render_minutes','render_per_video_minute',1)]
    costs={k: (number(prices[pk],pk)*usage[k]/div if k in usage and prices.get(pk) is not None else None) for k,pk,div in pairs}
    result={**run,'finished_at':now(),'wall_seconds':elapsed,'excluded_manual_audio_and_wait_seconds':excluded,
            'production_wall_seconds_excluding_declared_wait':elapsed-excluded,'usage':usage,'usage_evidence':receipt.get('evidence'),
            'actual_cost':sum(costs.values()) if all(v is not None for v in costs.values()) else None,
            'cost_items':costs,'currency':prices['currency'],'price_snapshot':copy.deepcopy(prices),
            'notes':'墙钟时间不是GPU/CPU时间；没有账单/调用回执时实际算力成本保持未知；手动网页配音不计入'}
    require(not usage or result['usage_evidence'],'填写实际用量时必须提供回执/日志依据')
    write(folder/f'制作总结_{run["id"]}.json',result);write(folder/'最新制作总结.json',result)
    path.unlink()
    return result
