"""Normalize the signed-in app-server catalog without inventing availability."""
import re


def latest_models(rows):
    visible={}
    for row in rows:
        if not isinstance(row,dict) or row.get('hidden'):continue
        model=row.get('model') or row.get('id')
        if isinstance(model,str) and model:visible[model]=row
    parsed=[]
    unversioned=[]
    for model,row in visible.items():
        match=re.fullmatch(r'gpt-(\d+(?:\.\d+)*?)-([a-z]+)(?:-(\d{4}-\d{2}-\d{2}))?',model or '')
        if match:
            parsed.append((tuple(map(int,match[1].split('.'))),match[2],match[3] or '',model,row))
        elif isinstance(model,str) and model:
            unversioned.append((None,None,model,row))
    selected={}
    for version,family,date,model,row in parsed:
        if family not in selected or (version,date) > selected[family][:2]:selected[family]=(version,date,model,row)
    result=[]
    for _,_,model,row in list(selected.values())+unversioned:
        levels=row.get('supportedReasoningEfforts') or []
        if not isinstance(levels,list):continue
        efforts=[v['reasoningEffort'] for v in levels if isinstance(v,dict) and isinstance(v.get('reasoningEffort'),str) and v['reasoningEffort']]
        if not efforts and isinstance(row.get('defaultReasoningEffort'),str) and row['defaultReasoningEffort']:
            efforts=[row['defaultReasoningEffort']]
        if not efforts:continue
        result.append({'id':model,'name':row.get('displayName',model),'efforts':efforts,
                       'default_effort':row.get('defaultReasoningEffort') if row.get('defaultReasoningEffort') in efforts else efforts[0]})
    return sorted(result,key=lambda r:r['id'])


def resolve_selection(models,model,effort):
    selected=next((m for m in models if m['id']==model),None)
    if not selected:raise ValueError('selected model is unavailable; refresh model settings')
    effort=effort or selected['default_effort']
    if effort not in selected['efforts']:raise ValueError('unsupported reasoning effort')
    return model,effort
