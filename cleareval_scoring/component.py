"""Deterministic, source-bound Bio component for the tissue-clearing benchmark.

No gold labels, answer IDs, old scores or network calls enter score_branch().
The frozen pilot parser supplies proposals; explicit checks decide credit.
"""
from pathlib import Path
import sys, re, copy
import numpy as np

from . import operations as op
from .binding import bind_operation
from .graph_refinement import graph_features, score as graph_score
from .capacity_metrics import align, aggregate
from . import condition_verifier as conditions
from . import recipe_verifier as recipes
from . import process_verifier as process
from . import scope_verifier as scope

VERSION='verified-bio-tissue-clearing-v5.4'
THRESHOLD=.70
CHECK_SCOPE=['material_identity','action','concentration','stock_dilution','duration','temperature','pH','agitation','polarity','reference_sequence']
CHECK_SCOPE+=['declared_recipe','declared_process_order','within_operation_condition_consistency']
# Source-vocabulary coverage additions, frozen before benchmark execution.
op.MATERIALS.update({
 'acetone':[r'\bacetone\b','丙酮'],
 'eci':[r'ethyl\s+cinnamate',r'\bECi\b'],
 'flyclear1':[r'FlyClear\s+Solution[-\s]*1'],
 'flyclear2':[r'FlyClear\s+Solution[-\s]*2'],
 'clearsee':[r'ClearSee(?![A-Za-z])'],
 'cubic_l':[r'CUBIC[-\s]*L(?!\w)'],
 'cubic_r':[r'CUBIC[-\s]*R(?![\w+])'],
 'cubic_ra':[r'CUBIC[-\s]*RA(?!\w)'],
 'cubic_rplus':[r'CUBIC[-\s]*R\+'],
 'macs0':[r'MACS[-\s\u2010-\u2015]*R0'],
 'macs1':[r'MACS[-\s\u2010-\u2015]*R1'],
 'macs2':[r'MACS[-\s\u2010-\u2015]*R2'],
})
op.FORMULATIONS.update({'flyclear1','flyclear2','clearsee','cubic_l','cubic_r','cubic_ra','cubic_rplus','macs0','macs1','macs2'})
for key in op.MATERIALS:
    if key.startswith('scales'):
        op.MATERIALS[key]=[p.replace(r'(?![\dD.])',r'(?![\dD]|\.\d)') for p in op.MATERIALS[key]]
CORE=re.compile(r'clear|dehydrat|delipid|refractive|\bRI\b|decalci|decolor|descal|透明|脱水|脱脂|折射|脱钙|脱色|复水',re.I)
LABEL=re.compile(r'immun|stain|label|antibod|blocking|permeab|免疫|染色|标记|抗体|封闭|通透|渗透',re.I)
NUMBER=r'\d+(?:\.\d+)?'
def domain_heading(text):
    # Relative temporal annotations do not change a section's operation type.
    return re.sub(r'\([^)]*\)|（[^）]*）','',text)
def combine(states):
    return 'FAIL' if 'FAIL' in states else 'UNKNOWN' if 'UNKNOWN' in states else 'PASS'
def normalize(text):
    for x,y in [('小时',' hours'),('分钟',' minutes'),('秒',' seconds'),('天',' days'),('室温',' RT'),('℃',' °C'),('摄氏度',' °C'),('过夜',' overnight')]:
        text=text.replace(x,y)
    return text
def number_interval(text,name):
    text=normalize(text)
    label='Time|时间' if name=='duration' else 'Temperature|温度'
    m=re.search(r'(?:'+label+r')\s*[:：]\s*([^;)）]+)',text,re.I)
    segment=m[1] if m else text
    if name=='duration' and re.search(r'\bovernight\b|\bON\b',segment,re.I) and not re.search(r'\d+\s*(?:hours?|hrs?|h)\b',segment,re.I):
        return dict(value='OVERNIGHT',kind='symbolic')
    if name=='temperature' and re.search(r'\bRT\b|room temperature',segment,re.I):
        remainder=re.sub(r'\bRT\b|room temperature','',segment,flags=re.I)
        other=number_interval(remainder,name)
        if other['value'] is not None and re.search(r'\bor\b|或',segment,re.I):
            return dict(value=None,kind='alternatives',choices=[dict(value='RT',kind='symbolic'),other])
        return dict(value='RT',kind='symbolic')
    regex=(r'(?<![\w])('+NUMBER+r')(?:\s*[-–—~至]\s*('+NUMBER+r'))?\s*(hours?|hrs?|h|minutes?|mins?|min|days?|d|seconds?|secs?|s)\b'
           if name=='duration' else r'(?<![\w])(-?'+NUMBER+r')(?:\s*[-–—~至]\s*(-?'+NUMBER+r'))?\s*(?:°\s*C|\bC\b)')
    matches=list(re.finditer(regex,segment,re.I))
    if not matches:return dict(value=None,kind='unparsed')
    vals=[];kinds=[]
    for m in matches:
        factor=(1440 if m[3].lower().startswith('d') else 60 if m[3].lower().startswith('h') else 1/60 if m[3].lower().startswith('s') else 1) if name=='duration' else 1
        vals.append([float(m[1])*factor,float(m[2] or m[1])*factor])
        before=segment[max(0,m.start()-18):m.start()]
        kinds.append('lower_strict' if re.search(r'>\s*$',before) else 'lower' if re.search(r'(?:at least|至少|≥)\s*$',before,re.I) else 'upper' if re.search(r'(?:at most|up to|≤|<)\s*$',before,re.I) else 'interval')
    if any(v!=vals[0] for v in vals) or re.search(r'larger .*longer|depending|according to|unspecified|以上|视.*而定',segment,re.I):
        return dict(value=None,kind='conditional_or_multiple')
    return dict(value=vals[0],kind=kinds[0])
def parameter_check(a,b):
    if a['kind']=='alternatives' or b['kind']=='alternatives':
        aset=a.get('choices',[a]);bset=b.get('choices',[b]);states=[]
        for candidate in bset:
            checks=[parameter_check(reference,candidate) for reference in aset]
            states.append('PASS' if 'PASS' in checks else 'UNKNOWN' if 'UNKNOWN' in checks else 'FAIL')
        return combine(states)
    av,bv=a['value'],b['value']
    if av is None or bv is None:return 'UNKNOWN'
    if isinstance(av,str) or isinstance(bv,str):return 'PASS' if av==bv else 'UNKNOWN'
    if b['kind']!='interval':return 'UNKNOWN'
    if a['kind'] in ('lower','lower_strict'):
        return 'PASS' if (bv[0]>av[0] if a['kind']=='lower_strict' else bv[0]>=av[0]) else 'FAIL' if bv[1]<av[0] else 'UNKNOWN'
    if a['kind']=='upper':return 'PASS' if bv[1]<=av[1] else 'FAIL' if bv[0]>av[1] else 'UNKNOWN'
    if av[0]-1e-8<=bv[0] and bv[1]<=av[1]+1e-8:return 'PASS'
    return 'FAIL' if bv[1]<av[0] or bv[0]>av[1] else 'UNKNOWN'
_legacy_interval=number_interval
_legacy_parameter_check=parameter_check
def number_interval(text,name):
    return conditions.parse(text,name,_legacy_interval)
def parameter_check(a,b):
    return conditions.compare(a,b,_legacy_parameter_check)
def concentration_fields(text,method):
    fields={}
    mentions=op.mentions(text,method)
    for m in mentions:
        before=text[max(0,m['start']-45):m['start']]
        hits=list(op.PERCENT.finditer(before))
        if hits:
            last=hits[-1];tail=before[last.end():]
            offset=max(0,m['start']-45)
            intervening=any(x['start']>=offset+last.end() and x['end']<=m['start'] for x in mentions if x!=m)
            if not intervening and len(tail)<30 and not re.search(r'[,，+;；]|\b(?:and|in|with)\b',tail,re.I):
                fields[m['id']]=float(last[1])
        after=re.match(r'\s*('+NUMBER+r')\s*%',text[m['end']:])
        if after:fields[m['id']]=float(after[1])
    return fields
def repeat_capacity(text):
    """Finite counts only; indefinite refreshes retain one declared occurrence."""
    t=text.lower()
    if re.search(r'^\s*optional\b|^\s*if\b|^\s*若|^\s*可选',t):
        return 1,False,'conditional_execution'
    direct_count=scope.explicit_count(text)
    if direct_count is not None and scope.each_duration(text):
        return direct_count,True,'explicit_total_occurrences_with_per_event_duration'
    trailing=re.search(r'(?:hours?|hrs?|h|min(?:utes)?|days?|小时|分钟|天)\s*[×x]\s*(\d+)',t)
    if trailing:return int(trailing[1]),True,trailing[0]
    for pattern,additional in [(r'repeat(?:ed)?\s+(once|twice)\b',True),(r'repeat(?:ed)?\s+(\d+)\s+times?\b',True),(r'重复\s*(\d+|一|两|二|三)\s*次',True),(r'(?:共|总共)\s*(\d+)\s*次',False),(r'(?<!\w)(\d+)\s*[×x]\s*(?=\d|with|次)',False)]:
        m=re.search(pattern,t)
        if m:
            v={'once':1,'twice':2,'一':1,'二':2,'两':2,'三':3}.get(m[1])
            if v is None:v=int(m[1])
            return v+int(additional),True,m[0]
    if re.search(r'^\s*repeat\s+\d+(?:\.\d+)?\s*%',t):
        return 1,True,'one_additional_numbered_reagent_operation'
    if re.search(r'repeat|refresh every|replace every|更换.*每天|每日.*换|重复',t):
        return 1,False,'endpoint_or_repeat_count_unresolved'
    return 1,True,'single_written_occurrence'
def representation(step,method):
    text=step['text'];heading=step.get('heading','')
    domain=domain_heading(heading)
    if LABEL.search(domain) and CORE.search(domain) and not LABEL.search(text):
        heading='Clearing'
    typed=op.typed_operation(text,heading,method)
    if 'gradient_index' in step and len(typed['primary_materials'])==1:
        typed['concentrations'][typed['primary_materials'][0]]=float(step['gradient_values'][step['gradient_index']])
    if re.search(r'1:1.*dilut|half',text,re.I) and not re.search(r'with full',text,re.I):
        if set(typed['primary_materials']) & op.FORMULATIONS:typed['stock_fraction_ranking_feature']=.5
    if re.search(r'(?:RI|refractive|折射).*(?:pretreat|预处理)|(?:clear|delipid|脱脂).*(?:pretreat|预处理)',heading,re.I):
        typed['phase']='ri_matching' if re.search(r'RI|refractive|折射',heading,re.I) else 'clearing'
    if typed['primary_materials'] and typed['action'] is None and CORE.search(heading):
        typed['action']='incubate';typed['action_origin']='medium_in_execution_section'
    # A numeral in a reagent name is never interpreted as a time.
    masked=list(text)
    for m in typed['material_spans']:masked[m['start']:m['end']]=' '*(m['end']-m['start'])
    typed['duration']=scope.duration(''.join(masked),step,conditions.parse,_legacy_interval)
    typed['temperature']=number_interval(''.join(masked),'temperature')
    if typed['action'] is None and typed['primary_materials'] and heading and typed['duration']['value'] is not None:
        typed['action']='incubate';typed['action_origin']='numbered_medium_contact_with_explicit_duration'
    return dict(text=text,heading=heading,typed=typed)
def features(steps,method):
    nodes=[representation(s,method) for s in steps];graph=graph_features(nodes)
    # Preserve the expanded parameter parser and relative phase anchor after base binding.
    for n,g in zip(nodes,graph):
        for k in ('duration','temperature'):g['features'][k]=n['typed'][k]
        if re.search(r'(?:RI|refractive|折射).*(?:pretreat|预处理)|(?:clear|delipid|脱脂).*(?:pretreat|预处理)',n['heading'],re.I):
            g['features']['phase']=n['typed']['phase']
        g['goal']='rehydrate' if re.search(r'rehydrat|复水',n['heading'],re.I) and not re.search(r'decolori|clear|脱色|透明',n['heading'],re.I) else 'dehydrate' if re.search(r'dehydrat|脱水',n['heading']+' '+n['text'],re.I) else None
    return graph
def split_gradients(steps):
    """Only explicitly enumerated finite gradients; preserve original row and span."""
    result=[]
    pattern=r'(?:'+NUMBER+r'\s*%\s*(?:[,/、，]\s*(?:and\s*)?|and\s+)){1,}'+NUMBER+r'\s*%'
    slash=r'(?:'+NUMBER+r'\s*/\s*){1,}'+NUMBER+r'\s*%'
    for step in steps:
        text=step['text'];group=None
        if re.search(r'gradient|graded|series|梯度',text,re.I):
            group=re.search(pattern,text,re.I) or re.search(slash,text,re.I)
        if group:
            values=re.findall(NUMBER,group[0])
            if len(values)<=20:
                for i,value in enumerate(values):
                    s=copy.deepcopy(step)
                    s.update(id=step['id']+':g'+str(i+1),original_id=step['id'],gradient_index=i,
                             gradient_values=values,original_text=text,
                             text=text[:group.start()]+value+'%'+text[group.end():])
                    result.append(s)
                continue
        result.append(copy.deepcopy(step))
    return result
def scope_candidates(steps,refs,method):
    desired=set().union(*(set(r['features']['primary_materials']) for r in refs)) if refs else set()
    phases={r['features']['phase'] for r in refs}
    label_positions=[i for i,s in enumerate(steps) if LABEL.search(domain_heading(s.get('heading',''))) and (not CORE.search(domain_heading(s.get('heading',''))) or LABEL.search(s['text']))]
    last_label=max(label_positions,default=-1)
    solvent_reference=any(set(r['features']['primary_materials']) & {'methanol','ethanol','tert_butanol','thf'} for r in refs)
    final_dehydration=solvent_reference and last_label>=0 and any(i>last_label and not LABEL.search(domain_heading(s.get('heading',''))) and re.search(r'dehydrat|脱水',domain_heading(s.get('heading','')),re.I) for i,s in enumerate(steps))
    included=[];excluded=[]
    for index,s in enumerate(steps):
        g=features([s],method)[0];f=g['features'];head=domain_heading(s.get('heading',''))
        reason=None
        if LABEL.search(head) and (not CORE.search(head) or LABEL.search(s['text'])):reason='labeling_outside_reference_inventory'
        elif final_dehydration and index<last_label and set(f['primary_materials']) & {'methanol','ethanol','tert_butanol','thf','dcm'}:reason='prelabel_solvent_episode_before_final_dehydration'
        elif re.search(r'rehydrat|复水',head,re.I) and not re.search(r'decolori|clear|脱色|透明',head,re.I) and not any(r.get('goal')=='rehydrate' for r in refs):reason='rehydration_is_not_reference_dehydration'
        elif re.search(r'fixation|perfus|采样|固定|灌注|取材',head,re.I):reason='preparation_outside_reference_inventory'
        elif f['phase'] in ('storage','mounting') and f['phase'] not in phases:reason='storage_or_imaging_outside_reference_inventory'
        elif not CORE.search(head) and not (set(f['primary_materials']) & desired):reason='no_reference_scope_anchor'
        if reason:excluded.append(dict(id=s['id'],reason=reason))
        else:included.append(s)
    return included,excluded
def correspondence_score(a,b):
    if a.get('goal') and b.get('goal') and a['goal']!=b['goal']:return -1.
    score=graph_score(a,b)
    if a['purpose']==b['purpose']=='wash' and a['input_medium_state']:
        if not b['input_medium_state']:score-=.25
        elif not set(a['input_medium_state']) & set(b['input_medium_state']):score-=.25
    return score
def alternative_sets(text,materials):
    # Explicit named alternatives allow either identity; a chemical mixture requires all.
    if re.search(r'\bor\b|或',text,re.I) and len(materials)>1 and set(materials)<=op.FORMULATIONS:
        return [{m} for m in materials]
    return [set(materials)]
def checks(rs,cs,rg,cg,method,*,enhanced=True):
    a,b=rg['features'],cg['features'];am,bm=set(a['primary_materials']),set(b['primary_materials'])
    identity='UNKNOWN' if not am or not bm else 'PASS' if all(any(x==y for x in alternative_sets(rs['text'],am)) for y in alternative_sets(cs['text'],bm)) else 'FAIL'
    act='UNKNOWN' if not a['action'] or not b['action'] else 'PASS' if a['action']==b['action'] else 'FAIL'
    result={'material_identity':identity,'action':act,'polarity':'PASS' if b['polarity']=='AFFIRMED' else 'FAIL'}
    if re.search(r'^\s*optional\b|^\s*if\b|^\s*若|^\s*可选',cs['text'],re.I):
        result['execution_branch']='UNKNOWN'
    if rg['purpose']!=cg['purpose'] and 'degassing' in (rg['purpose'],cg['purpose']):result['action']='FAIL'
    ca,cb=concentration_fields(rs['text'],method),concentration_fields(cs['text'],method)
    if 'gradient_index' in cs and len(bm)==1:cb[next(iter(bm))]=float(cs['gradient_values'][cs['gradient_index']])
    medium=re.search(r'\(?Medium\s*:\s*([^;)\n]+)',cs['text'],re.I)
    if medium:
        body=cs['text'][:medium.start()]
        body_mat=set(op.typed_operation(body,'',method)['primary_materials'])
        field_mat=set(op.typed_operation(medium[1],'',method)['primary_materials'])
        if body_mat and field_mat and not body_mat & field_mat:result['internal_material_consistency']='FAIL'
        elif field_mat and not body_mat and re.search(r'\b(?:in|with)\b',body,re.I):result['internal_material_consistency']='UNKNOWN'
    for material,value in ca.items():result['concentration:'+material]='UNKNOWN' if material not in cb else 'PASS' if abs(cb[material]-value)<1e-8 else 'FAIL'
    if enhanced:
        mixture=conditions.mixture_checks(rs['text'],cs['text'],ca,cb,op.mentions,method)
        for material,status in mixture.items():result['concentration:'+material]=status
    # Explicit stock dilution, unlike a ranking default, is an actual constraint.
    if re.search(r'half|1:1.*dilut|full|undiluted',rs['text'],re.I) and am & op.FORMULATIONS:
        ar=.5 if re.search(r'half|1:1.*dilut',rs['text'],re.I) and not re.search(r'with full',rs['text'],re.I) else 1.
        br=b.get('stock_fraction_ranking_feature')
        result['stock_dilution']='UNKNOWN' if br is None else 'PASS' if ar==br else 'FAIL'
    for name,regex in [('duration',r'\bTime\s*:|\b(?:for|until|overnight|ON)\b|时间|过夜'),('temperature',r'Temperature|°|℃|\bRT\b|room temperature|\d\s*C\b|室温|温度')]:
        if a[name]['value'] is not None or re.search(regex,rs['text'],re.I):result[name]=parameter_check(a[name],b[name])
    ph=re.search(r'pH(?:\s*(?:adjusted\s+to|:))?\s*('+NUMBER+r')',rs['text'],re.I)
    if ph:
        cp=re.search(r'pH(?:\s*(?:adjusted\s+to|:))?\s*('+NUMBER+r')',cs['text'],re.I)
        result['pH']='UNKNOWN' if not cp else 'PASS' if float(ph[1])==float(cp[1]) else 'FAIL'
    if enhanced:
        agitation_source,agitation_origin=scope.agitation_text(cs,conditions.agitation)
        agitation=conditions.agitation_check(rs['text'],agitation_source)
        if agitation is not None:result['agitation']=agitation
    elif re.search(r'without shaking|do not rotate',rs['text'],re.I):
        forbidden='rotate' if 'do not rotate' in rs['text'].lower() else 'shak'
        neg=bool(re.search(r'without shak|no shak|do not (?:rotate|shake)|不.*(?:摇|转)|静置',cs['text'],re.I))
        pos=bool(re.search(forbidden,cs['text'],re.I))
        result['agitation']='PASS' if neg else 'FAIL' if pos else 'UNKNOWN'
    elif re.search(r'with.*shak|gentle.*shak|on a rotator',rs['text'],re.I):
        result['agitation']='PASS' if re.search(r'shak|rotat|轻摇|振荡|摇床|旋转',cs['text'],re.I) else 'UNKNOWN'
    return result
def restore_headings(case):
    case=copy.deepcopy(case);head='';headings={}
    for line in case.get('answer','').splitlines():
        text=line.strip().strip('*').strip()
        step=re.match(r'^(\d+\.\d+)\s+',text)
        heading=re.match(r'^\d+[.\s、]+\s*([^\d].*)',text)
        if step:headings[step[1]]=head
        elif heading:head=heading[1].strip()
    for s in case['candidate_steps']:
        if not s.get('heading') and headings.get(s['id']):
            s['heading']=headings[s['id']]
            s['heading_origin']='original_answer_numbered_section'
    return case
def score_branch(case,*,recipe_enabled=True,process_enabled=True):
    case=restore_headings(case)
    refs=case['reference_steps'];rg=features(refs,case['method'])
    logical=split_gradients(case['candidate_steps'])
    cands,excluded=scope_candidates(logical,rg,case['method']);cg=features(cands,case['method'])
    n,m=len(refs),len(cands);scores=np.array([[correspondence_score(a,b) for b in cg] for a in rg],dtype=float).reshape(n,m)
    # When correspondence scores tie, prefer explicit compatible operations.
    # Time/temperature/reference applicability never enter this preference.
    preference=np.zeros((n,m),dtype=np.int8)
    for i in range(n):
        for j in range(m):
            if scores[i,j]<=THRESHOLD:continue
            ck=checks(refs[i],cands[j],rg[i],cg[j],case['method'])
            core=[v for k,v in ck.items() if k in {'material_identity','action','polarity','execution_branch','stock_dilution','internal_material_consistency'} or k.startswith('concentration:')]
            preference[i,j]=2 if 'FAIL' in core else 1 if 'UNKNOWN' in core else 0
    rcap=[r['occurrences'] for r in refs];counts=[repeat_capacity(c['text']) for c in cands];ccap=[x[0] for x in counts]
    recipe_index=recipes.index_claims(case.get('answer',''),case['method'],op.mentions) if case['candidate_steps'] else {}
    named=set().union(*(set(r['features']['primary_materials']) & op.FORMULATIONS for r in rg)) if rg else set()
    recipe_audit={name:recipes.evaluate(name,case.get('reference_id',''),recipe_index) for name in sorted(named)}
    process_audit=process.evaluate(case)
    # Both row and occurrence views use exactly the same operation evidence.
    matrices={}
    for mode,rc,cc in [('written',[1]*n,[1]*m),('occurrence',rcap,ccap)]:
        flow=align(scores,rc,cc,THRESHOLD,preference=preference);pairs=[];ids=np.full((n,m),'UNKNOWN',dtype='<U7');ver=ids.copy()
        positions=[(int(i),int(j)) for i,j in zip(*np.nonzero(flow))]
        for i,j in positions:
            ck=checks(refs[i],cands[j],rg[i],cg[j],case['method'])
            if recipe_enabled:
                for name in set(rg[i]['features']['primary_materials']) & set(cg[j]['features']['primary_materials']):
                    audit=recipe_audit.get(name,{})
                    if audit.get('status') in ('PASS','FAIL','UNKNOWN'):ck['declared_recipe:'+name]=audit['status']
            if process_enabled and cands[j].get('original_id',cands[j]['id']) in process_audit['failed_candidate_ids']:
                ck['declared_process_order']='FAIL'
            inversions=[(ii,jj) for ii,jj in positions if (i-ii)*(j-jj)<0]
            ck['reference_sequence']='FAIL' if inversions else 'PASS'
            ids[i,j]=combine([ck['material_identity'],ck['action']]);ver[i,j]=combine(list(ck.values()))
            pairs.append(dict(reference=refs[i]['id'],candidate=cands[j]['id'],count=int(flow[i,j]),score=round(float(scores[i,j]),5),
                              checks=ck,identity=ids[i,j],verification=ver[i,j],
                              inversions=[dict(reference=refs[ii]['id'],candidate=cands[jj]['id']) for ii,jj in inversions]))
        metrics=aggregate(flow,ids,ver,rc,cc)
        if not case['candidate_steps']:
            metrics['operation_SR']=None;metrics['verified_Bio_SR']=None;metrics['conditional_SR_upper']=None
        matrices[mode]=dict(metrics=metrics,pairs=pairs)
    unknown_counts=[dict(id=c['id'],reason=count[2]) for c,count in zip(cands,counts) if not count[1]]
    reference_unknown_counts=[dict(id=r['id'],reason='reference_refresh_schedule_not_compiled') for r in refs
                              if re.search(r'refresh every|refresh at least|repeat.*more than|every two days',r['text'],re.I)]
    # Numbered execution order is retained; contradictory "before" headings are surfaced.
    phase_conflicts=[]
    seen_ri=False
    for c in case['candidate_steps']:
        h=c.get('heading','')
        if re.search(r'refractive|\bRI\b|折射',h,re.I):seen_ri=True
        if seen_ri and LABEL.search(h) and (not CORE.search(h) or LABEL.search(c['text'])):
            phase_conflicts.append(dict(id=c['id'],kind='labeling_numbered_after_RI',explicit_before_claim=bool(re.search(r'before|之前|前进行',h,re.I))))
    matched_ref={p['reference'] for p in matrices['written']['pairs']}
    diagnostics=[]
    for i,r in enumerate(refs):
        if r['id'] in matched_ref or not m:continue
        j=max(range(m),key=lambda j:scores[i,j])
        diagnostics.append(dict(reference=r['id'],best_candidate=cands[j]['id'],score=round(float(scores[i,j]),5),
                                checks=checks(r,cands[j],rg[i],cg[j],case['method']),credited=False))
    return dict(version=VERSION,check_scope=CHECK_SCOPE,reference_scope='existing_reference_inventory',
                reference_groups=n,candidate_groups=m,excluded=excluded,scope_complete=bool(case['candidate_steps']),
                occurrence_count_complete=not unknown_counts and not reference_unknown_counts,unknown_counts=unknown_counts,
                reference_unknown_counts=reference_unknown_counts,
                recipe_audit=recipe_audit,process_audit=process_audit,
                candidate_ids=[c['id'] for c in cands],logical_candidate_steps=cands,**matrices,unmatched_diagnostics=diagnostics,
                phase_order_conflicts=phase_conflicts,recipe_expansion_verified='explicit_claims_only')

def apply_to_result(result,case):
    """Optional component hook. Keeps old Bio metrics; adds a versioned experiment namespace.

    Current Co/Com/Eff/IA formulas do not consume these supplementary metrics.
    """
    out=copy.deepcopy(result);packet=score_branch(case)
    out.setdefault('supplementary_components',{})['verified_bio_v3']=packet
    return out
