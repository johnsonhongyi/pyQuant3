"""Project ownership and readable indexes for automated Muse research threads."""
from datetime import datetime,timedelta,timezone
import hashlib
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PROJECT_ROOT=ROOT/'muse-research'
PROJECT_NAME='Muse 模拟策略'
HK=timezone(timedelta(hours=8))
STAGES={'premarket':'盘前','intraday':'盘中','interactive':'问答','post_close_review':'盘后','execution_review':'成交复盘'}


def clean(value,limit=120):
    return ' '.join(str(value or '').split()).replace('|','／')[:limit]


def ensure_project(app):
    PROJECT_ROOT.mkdir(exist_ok=True)
    cursor=None
    while True:
        response=app.request('project/list',{'limit':100,**({'cursor':cursor} if cursor else {})})
        for project in response['data']:
            if project['name']==PROJECT_NAME and any(os.path.normcase(r['path'])==os.path.normcase(str(PROJECT_ROOT)) for r in project['roots']):return project['id']
        cursor=response.get('nextCursor')
        if not cursor:break
    return app.request('project/create',{'idempotencyKey':'muse-research-'+hashlib.sha256(str(PROJECT_ROOT).casefold().encode()).hexdigest()[:24],
        'name':PROJECT_NAME,'roots':[{'path':str(PROJECT_ROOT)}],'metadata':{'purpose':'stockstrategy.paper.research'}})['project']['id']


def thread_title(job,result=None,status='分析中'):
    context=job.get('context',{});scope=context.get('validation_scope','production_paper')
    stage='合成验收' if 'synthetic' in scope else '桌面验收' if 'isolated' in scope else STAGES.get(context.get('workflow_stage'),'研究')
    try:at=datetime.fromisoformat(context.get('as_of','').replace('Z','+00:00')).astimezone(HK).strftime('%m-%d %H:%M')
    except (ValueError,TypeError):at=clean(context.get('trade_date','未知日期'),10)
    plans=(result or {}).get('proposal',{}).get('plans',[])
    focus=sorted(enumerate(plans),key=lambda p:({'follow':0,'observe':1,'avoid':2}.get(p[1].get('action'),3),p[0]))
    stocks=context.get('stocks',[]);names={s['symbol']:s.get('name','') for s in stocks}
    codes=[p['symbol'] for _,p in focus[:2]] or [s['symbol'] for s in stocks[:2]]
    label='/'.join(c.split('.')[0]+clean(names.get(c,''),4) for c in codes) or '全市场'
    if plans:status='跟%d 观%d 避%d'%tuple(sum(p.get('action')==a for p in plans) for a in ('follow','observe','avoid'))
    tag='#'+clean(job['id'],6) if job.get('id') else 'T:'+clean(job.get('thread_id',''),8)
    return f'Muse｜{at}｜{stage}｜{label}｜{clean(status,24)} {tag}'


def report_path(job):
    identity=job.get('id') or job.get('thread_id','').replace('-','')
    if len(identity)!=32 or any(c not in '0123456789abcdef' for c in identity):raise ValueError('invalid research job id')
    return PROJECT_ROOT/'reports'/(identity+'.md')


def research_prompt(job):
    context=job['context'];selection=context.get('ai_runtime',{})
    codes='、'.join(s['symbol']+' '+clean(s.get('name',''),16) for s in context.get('stocks',[]))
    return '\n'.join((f'# {thread_title(job)}',f'任务：{job["id"]} · 证据时间：{context.get("as_of","")} ',
        f'模型配置：{selection.get("model","默认")} / {selection.get("reasoning_effort","默认")}',
        f'个股池：{codes or "空池"}',f'证据指纹：{job["evidence_hash"]}',
        f'[本轮研究摘要]({report_path(job).as_posix()})',
        '研究问题：'+(job.get('question') or '分析市场、资金轮动及池内个股，给出条件计划与缺口。'),
        '请调用 get_market_context 获取本轮冻结证据，并按需调用个股和 ATS 证据工具。',
        '先用简洁中文说明重点代码与关键结论，最终严格返回约定的结构化提案。'))


def summary_markdown(job,result):
    proposal=result['proposal'];context=job['context'];names={s['symbol']:s.get('name','') for s in context.get('stocks',[])}
    lines=[f'# {thread_title(job,result)}',f'任务 `{job.get("id") or "历史记录未登记"}` · 会话 `{result["thread_id"]}`',
           f'证据时间：{context.get("as_of","")} · 模型：{result.get("model","")} / {result.get("reasoning_effort","")}',
           '', '以下为已校验研究提案，成交与持仓以执行账本为准。','', '## 市场与资金',
           clean(proposal['market_view'],900),clean(proposal['rotation_view'],900),'', '## 个股重点',
           '| 股票代码 / 名称 | 计划 | 关键判断 | 失效条件 / 缺口 |','| --- | --- | --- | --- |']
    labels={'follow':'条件跟随','observe':'观察','avoid':'回避'}
    for plan in proposal['plans']:
        lines.append('| %s %s | %s | %s | %s；%s |'%(plan['symbol'],clean(names.get(plan['symbol'],''),20),
            labels.get(plan['action'],plan['action']),clean(plan['thesis'],220),clean(plan['invalidation'],180),clean('；'.join(plan['missing_data']),180)))
    lines+=['','## 问题回答',proposal['answer'],'',f'证据指纹：`{job["evidence_hash"]}`']
    return '\n'.join(lines)+'\n'


def publish_summary(app,job,result):
    title=thread_title(job,result);text=summary_markdown(job,result);path=report_path(job)
    path.parent.mkdir(exist_ok=True)
    temporary=path.with_suffix('.pending');temporary.write_bytes(text.encode('utf-8'));os.replace(temporary,path)
    write_index()
    app.request('thread/name/set',{'threadId':result['thread_id'],'name':title})
    result.update(thread_title=title,report_path=str(path),project_id=app.project_id)


def write_index():
    rows=[]
    for path in (PROJECT_ROOT/'reports').glob('*.md'):
        with path.open(encoding='utf-8') as stream:head=[stream.readline() for _ in range(3)]
        title=clean(head[0].removeprefix('# '),180)
        stamp=head[2].partition('证据时间：')[2].partition(' · ')[0].strip()
        try:key=datetime.fromisoformat(stamp.replace('Z','+00:00')).timestamp()
        except (ValueError,TypeError):key=0
        rows.append((key,f'| [{title}](reports/{path.name}) |'))
    lines=['# Muse 策略研究索引','','最近100份已校验提案；按证据时间排序。可按股票代码、任务类型或短ID查找。',
           '', '| 研究时间 / 类型 / 重点代码 / 结论 |','| --- |']
    lines.extend(row for _,row in sorted(rows,reverse=True)[:100])
    path=PROJECT_ROOT/'INDEX.md';temporary=path.with_suffix('.pending')
    temporary.write_bytes(('\n'.join(lines)+'\n').encode('utf-8'));os.replace(temporary,path)
