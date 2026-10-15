"""Normalize the signed-in app-server catalog without inventing availability."""
import re


def latest_models(rows):
    visible={r.get('model',r.get('id')):r for r in rows if not r.get('hidden')}
    parsed=[]
    for model,row in visible.items():
        match=re.fullmatch(r'gpt-(\d+(?:\.\d+)*?)-([a-z]+)(?:-(\d{4}-\d{2}-\d{2}))?',model or '')
        if match:
            parsed.append((tuple(map(int,match[1].split('.'))),match[2],match[3] or '',model,row))
    if not parsed:return []
    major=max(r[0][0] for r in parsed)
    selected={}
    for version,family,date,model,row in parsed:
        if version[0]!=major:continue
        if family not in selected or (version,date) > selected[family][:2]:selected[family]=(version,date,model,row)
    result=[]
    for _,_,model,row in selected.values():
        upgrade=row.get('upgrade')
        if isinstance(upgrade,str) and upgrade in visible:continue
        efforts=[v['reasoningEffort'] for v in row.get('supportedReasoningEfforts',[]) if v.get('reasoningEffort')]
        if not efforts:continue
        result.append({'id':model,'name':row.get('displayName',model),'efforts':efforts,
                       'default_effort':row.get('defaultReasoningEffort',efforts[0])})
    return sorted(result,key=lambda r:r['id'])


def resolve_selection(models,model,effort):
    selected=next((m for m in models if m['id']==model),None)
    if not selected:raise ValueError('selected model is unavailable; refresh model settings')
    effort=effort or selected['default_effort']
    if effort not in selected['efforts']:raise ValueError('unsupported reasoning effort')
    return model,effort
