"""Public plan evidence for publishing packets; never infers account eligibility."""
from datetime import datetime, timezone
from .core import read, require


def snapshot(root, platforms):
    path = root / '00_项目配置/平台收益计划索引.json'
    index = read(path) if path.exists() else {}
    require(isinstance(index, dict) and isinstance(index.get('platforms', {}), dict), '收益计划索引格式错误')
    checked = index.get('checked_at')
    fresh = False
    if checked:
        try:
            stamp = datetime.fromisoformat(checked)
            age = (datetime.now(timezone.utc) - stamp).total_seconds()
            fresh = 0 <= age <= 7 * 86400
        except (ValueError, TypeError):
            pass
    reports = {}
    for platform in platforms:
        plan = index.get('platforms', {}).get(platform, {})
        require(isinstance(plan, dict), '收益计划条目格式错误')
        reports[platform] = {
            'public_plan': plan,
            'account_status': 'NOT_VERIFIED',
            'account_note': '未读取本账号计划页；粉丝、权益、地区、原创及单条计收益资格均待核验。',
            'revenue_estimate': None,
            'review_status': 'RECENT_PUBLIC_RESEARCH_ACCOUNT_REVIEW_REQUIRED' if fresh and plan else 'PUBLIC_RULE_RECHECK_REQUIRED',
        }
    return {'checked_at': checked, 'fresh': fresh, 'platforms': reports,
            'notice': '公开计划与账号资格分开记录；没有实际结算数据时不预测收入。'}
