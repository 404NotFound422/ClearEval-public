"""Opt-in literal atomic alignment v3. No official score or legacy behavior changes.

Candidate roles use text and adjacent treatment sequence, never question/answer IDs.
Unknown evidence remains unknown; compatibility is not scientific correctness.
"""
from copy import deepcopy
import hashlib,json,re
from pathlib import Path
from oeq_simple_representation import operation_record, normalize_units
from oeq_simple_time import active_label_phase_text
VERSION='automatic-atomic-alignment-v3'
UNKNOWN='unresolved'
SCOPES={'requested_clearing':{'clearing','ri_matching_storage'},'supplemental_full_answer':{'pretreatment','immunolabeling','clearing','ri_matching_storage'}}

def parameter_selection(row):
    """Recognize only same-action/same-reagent concentration alternatives; do not choose."""
    text=row.get('operation','').lower();parts=re.split(r'\bor\b',text)
    default={'status':'NO_RECOGNIZED_PARAMETER_ALTERNATIVE','raw_alternatives':[]}
    if len(parts)<2:return default
    identities=[('dcm',r'\bdcm\b|\bdichloromethane\b|\bmethylene chloride\b'),
                ('methanol',r'\bmethanol\b|\bmeoh\b'),('dbe',r'\bdbe\b|\bdi[- ]?benzyl\s*ether\b')]
    choices=[];names=[]
    for i,part in enumerate(parts):
        found={name for name,pattern in identities if re.search(pattern,part)}
        values=re.findall(r'(?<![\d.\-])\d+(?:\.\d+)?\s*%',part)
        if len(found)!=1 or len(values)!=1:return default
        if i and re.search(r'\b(?:incubat\w*|wash\w*|rinse\w*|stor\w*|add\w*|use\w*|dehydrat\w*|rehydrat\w*)\b',part):return default
        names.append(next(iter(found)));choices.append(values[0])
    if len(set(names))!=1:return default
    return {'status':'UNRESOLVED_CONCENTRATION_SELECTION','raw_alternatives':choices,
            'reagent_identity':names[0],'selection':None,'policy':'treatment coverage retained; concentration correctness unresolved'}

def execution_status(row):
    """Scope modality to the treatment action, not manner, time, or imaging purpose."""
    assertion=row.get('assertion')
    if assertion is not None:
        polarity=assertion.get('polarity')
        if polarity=='CONDITIONAL':return 'OPTIONAL_OR_CONDITIONAL'
        if polarity=='NEGATED':return 'PROHIBITED_OR_OMITTED'
        if polarity!='AFFIRMED':return 'UNRESOLVED_SELECTION'
    t=row.get('operation','').lower()
    actions=r'(?:incubat\w*|wash\w*|rinse\w*|add\w*|use\w*|stor\w*|dehydrat\w*|rehydrat\w*|bleach\w*|block\w*|permeabili\w*)'
    if row.get('statement_mode')=='PROHIBITION' or re.search(r'\b(?:do not|must not|should not|never|avoid)\s+(?:be\s+)?'+actions+r'|^\s*(?:omit|skip)\b|\bnot\s+'+actions,t):
        return 'PROHIBITED_OR_OMITTED'
    if re.search(r'^\s*(?:optional(?:ly)?\b|if (?:needed|desired|required)\b|(?:can|may)\s+(?:be|use|incubat\w*|wash|stor\w*))|\b'+actions+r'\s+optionally\b',t):
        return 'OPTIONAL_OR_CONDITIONAL'
    treatment_clause=re.split(r'\b(?:after|before|following|prior to|to enable|to allow|for\s+(?:imaging|storage|light.sheet|confocal))\b',t,maxsplit=1)[0]
    # Small reagent identity vocabulary, not a sentence-level synonym framework.
    # OR must contrast identities; parenthetical aliases of one identity do not.
    entities=[('dcm',r'\bdcm\b|\bdichloromethane\b|\bmethylene chloride\b'),
              ('meoh',r'\bmeoh\b|\bmethanol\b'),('dbe',r'\bdbe\b|\bdi[- ]?benzyl\s*ether\b'),
              ('ptwh',r'\bpt\.?w\.?h\b'),('pbs',r'\bpbs\b'),('peroxide',r'\bh2o2\b|\bhydrogen peroxide\b')]
    mentions=sorted((m.start(),m.end(),name) for name,pattern in entities for m in re.finditer(pattern,treatment_clause))
    for alternative in re.finditer(r'\bor\b|\binstead of\b|\bas an alternative to\b',treatment_clause):
        left=[m for m in mentions if m[1]<=alternative.start()]
        right=[m for m in mentions if m[0]>=alternative.end()]
        if not left or not right:return 'UNRESOLVED_SELECTION'
        if left[-1][2]!=right[0][2]:return 'UNSELECTED_ALTERNATIVE'
        if parameter_selection(row)['status']=='UNRESOLVED_CONCENTRATION_SELECTION':continue
        # Same reagent does not make different concentrations/actions equivalent.
        # Exempt only a pure parenthetical name alias, never outside-bracket OR.
        alias_parent=next((m for m in re.finditer(r'\([^()]*\)',treatment_clause) if m.start()<alternative.start()<m.end()),None)
        if alias_parent:
            alias_text=alias_parent.group()[1:-1]
            for _,pattern in entities:alias_text=re.sub(pattern,'',alias_text)
            alias_text=re.sub(r'\bor\b|[,/\s]','',alias_text)
            if not alias_text:continue
        return 'UNSELECTED_ALTERNATIVE'
    if re.search(r'^\s*alternatively\b',treatment_clause):return 'UNRESOLVED_SELECTION'
    if row.get('statement_mode','OPERATION')!='OPERATION':return 'NON_OPERATION'
    return 'ASSERTED_OPERATION'

def composition(row):
    t=row['operation'].lower()
    if execution_status(row) in {'UNSELECTED_ALTERNATIVE','UNRESOLVED_SELECTION'}:return UNKNOWN
    t=re.split(r'\b(?:to wash|to remove|to eliminate|after|before|following|prior to)\b',t)[0]
    dcm=bool(re.search(r'\bdcm\b|dichloromethane|methylene chloride',t));meoh=bool(re.search(r'\bmethanol\b|\bmeoh\b',t))
    if re.search(r'h2o2|h₂o₂|hydrogen peroxide',t):return 'peroxide_methanol' if meoh else 'peroxide'
    if dcm:return 'dcm_methanol_mixture' if meoh else 'dcm_without_stated_cosolvent'
    if re.search(r'di\s*benzyl\s*ether|\bdbe\b',t):return 'dbe'
    if re.search(r'\b(?:thf|tetrahydrofuran)\b',t):return 'thf'
    if re.search(r'\bpt\.?w\.?h\b',t):return 'ptwh_named_buffer'
    if meoh:return 'methanol'
    return UNKNOWN

def phase_from_heading(heading):
    t=heading.lower()
    if re.search(r'refractive|\bri\b',t) and re.search(r'dehydration|delipidation|clearing',t):return UNKNOWN
    if re.search(r'refractive|\bri\b|storage|preservation|pre.imaging',t):return 'ri_matching_storage'
    if re.search(r'pre.treatment|pretreatment|pigment bleaching',t):return 'pretreatment'
    # Post-immunolabeling dehydration is a clearing heading, not antibody treatment.
    if re.search(r'dehydration|delipidation|optical clearing',t):return 'clearing'
    if active_label_phase_text(t)!=t:return UNKNOWN
    if re.search(r'immunolabel|immunostain|antibod|permeabili|blocking|counterstain|^\d*\s*labeling',t):return 'immunolabeling'
    return UNKNOWN

def annotate(rows, *, trusted_reference_phase=False):
    out=deepcopy(rows);last_label={}
    for r in out:
        t=re.split(r'\b(?:after|before|following|prior to)\b',r['operation'].lower())[0];h=r.get('phase','');c=composition(r); reasons=[]
        phase=r.get('comparison_phase',UNKNOWN) if trusted_reference_phase else phase_from_heading(h)
        role=UNKNOWN
        if re.search(r'\b(?:wash|rinse)\b',t) and re.search(r'\b(?:primary|secondary)\b',t):
            role='secondary_wash' if 'secondary' in t else 'primary_wash';reasons=['explicit_antibody_wash']
        elif re.search(r'\bprimary antibod',t):role='primary_labeling';reasons=['explicit_primary_antibody']
        elif re.search(r'\bsecondary antibod',t):role='secondary_labeling';reasons=['explicit_secondary_antibody']
        elif c.startswith('peroxide') or re.search(r'\bbleach',t):role='bleaching';reasons=['peroxide_or_bleaching']
        elif 'permeabilization' in t:role='permeabilization';reasons=['named_permeabilization']
        elif re.search(r'\bblock(?:ing)?\b',t):role='blocking';reasons=['explicit_blocking']
        elif c=='dcm_methanol_mixture':role='mixed_solvent_exchange';reasons=['dcm_and_methanol_in_treatment']
        elif c=='dcm_without_stated_cosolvent':role='pure_solvent_wash';reasons=['dcm_no_stated_cosolvent']
        elif c=='thf' and phase=='clearing':role='dehydration';reasons=['thf_in_explicit_clearing_heading']
        elif c=='dbe':role='storage' if re.search(r'\bstor',t) else 'ri_matching';reasons=['dbe_medium']
        elif re.search(r'\brehydrat',t):role='rehydration';reasons=['explicit_rehydration']
        elif re.search(r'\bdehydrat',t):role='dehydration';reasons=['explicit_dehydration']
        elif re.search(r'\bchill',t):role='chilling';reasons=['explicit_chilling']
        elif c=='methanol' and re.search(r'\bwash',t):role='methanol_wash';reasons=['methanol_wash']
        elif re.search(r'ptx\.?2|triton',t) and re.search(r'\bwash|incubat',t):role='detergent_wash';reasons=['detergent_treatment']
        if not trusted_reference_phase and role in {'permeabilization','blocking','primary_labeling','secondary_labeling'} and phase!='immunolabeling':
            phase=UNKNOWN;reasons.append('role_heading_scope_requires_review')
        # A combined heading cannot assign all reagent operations to its final stage.
        if not trusted_reference_phase and phase==UNKNOWN and re.search(r'dehydration|delipidation|clearing',h,re.I) and re.search(r'refractive|\bri\b',h,re.I):
            if role in {'ri_matching','storage'}:phase='ri_matching_storage'
            elif role in {'dehydration','mixed_solvent_exchange','pure_solvent_wash'} or c=='methanol':phase='clearing'
        state=execution_status(r)
        if state!='ASSERTED_OPERATION':role=UNKNOWN;reasons=['nonasserted_operation:'+state]
        key=(r.get('branch','main'),phase,h)
        if role in {'primary_labeling','secondary_labeling'}:last_label[key]=role.split('_')[0]
        if state=='ASSERTED_OPERATION' and role==UNKNOWN and re.search(r'\bwash|\brinse',t) and c=='ptwh_named_buffer' and key in last_label:
            role=last_label[key]+'_wash';reasons=['preceding_explicit_antibody_in_same_heading_branch']
        if role not in {'primary_labeling','secondary_labeling','primary_wash','secondary_wash'}:last_label.pop(key,None)
        r.update(comparison_phase=phase,operation_role=role,role_evidence=reasons,composition=c,execution_status=state,parameter_selection_status=parameter_selection(r))
    # Infer direction only inside a contiguous methanol sequence in the same heading.
    i=0
    while i<len(out):
        r=out[i]
        if r['execution_status']!='ASSERTED_OPERATION' or r['composition']!='methanol' or r['operation_role'] not in {UNKNOWN,'methanol_wash'}:i+=1;continue
        j=i+1
        while j<len(out) and out[j]['execution_status']=='ASSERTED_OPERATION' and out[j]['composition']=='methanol' and out[j]['phase']==r['phase'] and out[j].get('branch')==r.get('branch') and out[j]['operation_role'] in {UNKNOWN,'methanol_wash'}:j+=1
        vals=[]
        for x in out[i:j]:
            v=re.findall(r'(\d+(?:\.\d+)?)\s*%',x['operation']);vals.append(float(v[0]) if len(v)==1 else None)
        differences=[b-a for a,b in zip(vals,vals[1:]) if a is not None and b is not None and a!=b]
        direction='dehydration' if differences and all(x>0 for x in differences) else 'rehydration' if differences and all(x<0 for x in differences) else UNKNOWN
        for x in out[i:j]:
            if x['operation_role']==UNKNOWN and direction!=UNKNOWN:x.update(operation_role=direction,role_evidence=['contiguous_monotone_methanol_series'])
        if direction=='rehydration' and j<len(out) and re.search(r'\bpbs\b',out[j]['operation'],re.I) and out[j]['phase']==r['phase'] and out[j].get('branch')==r.get('branch') and out[j]['execution_status']=='ASSERTED_OPERATION' and out[j]['operation_role']==UNKNOWN:
            out[j].update(operation_role='rehydration',role_evidence=['pbs_immediately_after_descending_methanol_series'])
        i=j
    # An explicit descending series can already carry rehydration roles; use its
    # immediate PBS endpoint too, without inferring a general PBS synonym.
    for prev,row in zip(out,out[1:]):
        if row['operation_role']==UNKNOWN and row['execution_status']=='ASSERTED_OPERATION' and prev['operation_role']=='rehydration' and row['phase']==prev['phase'] and row.get('branch')==prev.get('branch') and re.search(r'\bpbs\b',row['operation'],re.I):
            row.update(operation_role='rehydration',role_evidence=['pbs_immediately_after_rehydration'])
    return out

def split_occurrences(row, *, repeat_scenario=None):
    """Explicit repeat/list only; retain unresolved ranges and group time. Mixtures stay one."""
    t=row['operation'];raw=row['raw_text'];count=1;status='single_literal';treatments=[t];group={}
    repeat=re.search(r'\b(\d+)\s*(?:[-–]|to)\s*(\d+)\s*(?:times|washes|solution changes)\b',raw,re.I)
    if repeat:
        lo,hi=map(int,repeat.groups());group['repeat_range']=[lo,hi]
        if repeat_scenario is None:status='unresolved_repeat_range'
        elif not lo<=repeat_scenario<=hi:raise ValueError('Repeat scenario outside literal range')
        else:count=repeat_scenario;status='explicit_repeat_scenario'
    else:
        m=re.search(r'\b(\d+)\s+(?:times|washes|solution changes)\b|\b(twice|thrice)\b',raw,re.I)
        if m:count=int(m[1]) if m[1] else {'twice':2,'thrice':3}[m[2].lower()];status='explicit_repeat'
    from oeq_representation_consistency import explicit_replacement_count
    replacement=explicit_replacement_count(row)
    if replacement and replacement['count'] is not None and status in {'single_literal','explicit_repeat'}:
        count=replacement['count'];status='explicit_replacement_plus_initial'
        group['replacement_evidence']=replacement
    elif replacement and replacement['count'] is None:
        count=1;status='unresolved_conflicting_count';group['replacement_evidence']=replacement
    # Only an explicit sequence marker and one methanol concentration list qualify.
    serial=re.search(r'((?:\d+(?:\.\d+)?\s*%\s*[,→]\s*)+\d+(?:\.\d+)?\s*%)',t)
    if serial and composition(row)=='methanol' and re.search(r'\b(?:series|sequential|graded|dehydrat|rehydrat)',t,re.I):
        values=re.findall(r'\d+(?:\.\d+)?\s*%',serial[1]);treatments=[t[:serial.start()]+v+t[serial.end():] for v in values];status='explicit_serial_list'
    else:treatments=[t]*count
    if execution_status(row)!='ASSERTED_OPERATION':
        treatments=[t];status='nonasserted_not_expanded'
    duration_pattern=r'\b(?:\d+(?:\.\d+)?(?:\s*(?:[-–]|to)\s*\d+(?:\.\d+)?)?\s*(?:hours?|hrs?|h|minutes?|mins?|days?|d)|overnight)\b'
    mentions=[{'raw':m.group(),'start':m.start(),'end':m.end()} for m in re.finditer(duration_pattern,raw,re.I)]
    if len(treatments)>1:
        # EACH must qualify a duration, not a temperature or a different clause.
        each_pattern=duration_pattern+r'\s*(?:for\s+)?(?:each(?:\s+(?:wash|step|incubation))?|per\s+(?:wash|step|incubation))\b'
        each_before=r'\b(?:each|per)\s+(?:wash|step|incubation)\s*(?:for|:|of|takes)?\s*('+duration_pattern+r')'
        each=list(re.finditer(each_pattern,raw,re.I))+list(re.finditer(each_before,raw,re.I))
        # Explicit total always wins. No inferred division of group total.
        total=bool(re.search(r'\b(?:total|in total|overall|over\s+\d)\b',raw,re.I))
        scope='EACH' if each and not total else 'GROUP_OR_UNSPECIFIED'
        group={'duration_scope':scope,'duration_mentions':mentions,**group}
        if 'time' in row.get('parameters',{}):group['original_time_field']=deepcopy(row['parameters']['time'])
        if scope=='GROUP_OR_UNSPECIFIED':
            group['time']=deepcopy(row.get('parameters',{}).get('time')) or {'raw':'; '.join(m['raw'] for m in mentions),'normalized':'; '.join(normalize_units(m['raw']) for m in mentions)}
            group['per_occurrence_time']='UNSPECIFIED'
        else:
            each_durations=[m.group() for item in each for m in re.finditer(duration_pattern,item.group(),re.I)]
            group['per_occurrence_time']={'raw':'; '.join(dict.fromkeys(each_durations)),'normalized':'; '.join(normalize_units(x) for x in dict.fromkeys(each_durations))}
    out=[]
    for i,text in enumerate(treatments,1):
        x=deepcopy(row)
        if len(treatments)>1:
            # Parent raw stays intact. The derived occurrence never re-embeds group duration.
            text=re.sub(duration_pattern,'',text,flags=re.I)
            text=re.sub(r'\b\d+\s*(?:times|washes|solution changes)\b|\b(?:twice|thrice)\b','',text,flags=re.I)
            text=re.sub(r'\b(?:over|for|in total|total)\s*(?=[.;,)]|$)','',text,flags=re.I)
            text=re.sub(r'\b(?:of|for|over|during)\s*(?:each)?(?=\s*(?:[.;,)]|$|with\b))','',text,flags=re.I)
            text=re.sub(r'\s+([.;,])',r'\1',text)
            text=re.sub(r'\s+',' ',text).strip()
            x.get('parameters',{}).pop('time',None)
            x['parameter_mentions']=[p for p in x.get('parameter_mentions',[]) if p['kind']!='duration']
            if group['duration_scope']=='EACH':x.setdefault('parameters',{})['time']=deepcopy(group['per_occurrence_time'])
        x.update(id=f"{row['id']}.{i:02d}",parent_record_id=row['id'],operation=text,reagent_text=text,scoring_text=text,occurrence_index=i,occurrence_count=len(treatments),atomization=status,group_parameters=deepcopy(group))
        if x.get('parameters'):x['scoring_text']+=' | '+'; '.join(k+': '+v['normalized'] for k,v in x['parameters'].items())
        x['text_origin']='DERIVED_OCCURRENCE' if len(treatments)>1 else 'LITERAL';out.append(x)
    return out

def candidate_from_records(candidate, *, repeat_scenario=None):
    rows=[];groups=[]
    for row in candidate['operations']:
        expanded=split_occurrences(row,repeat_scenario=repeat_scenario)
        if any(x['group_parameters'] for x in expanded):
            groups.append({'id':row['id'],'source':deepcopy(row.get('source')),'raw_text':row['raw_text'],
                           'parameters':deepcopy(expanded[0]['group_parameters'])})
            for x in expanded:
                x['group_parameters']={'group_id':row['id'],'duration_scope':x['group_parameters'].get('duration_scope'),
                                       'parameter_reference':'occurrence_groups; group totals stored once'}
        rows.extend(expanded)
    return {**deepcopy(candidate),'schema_version':VERSION,'operations':annotate(rows),'occurrence_groups':groups}

def candidate_from_text(protocol):
    """Strict hierarchical numbered fallback; source spans are exact, unrecognized lines reported."""
    rows=[];heading='';offset=0;unparsed=[]
    for line in protocol.splitlines(keepends=True):
        if re.match(r'^\s*\d+\.\d+\s+',line):
            rows.append(operation_record(line.strip(),record_id=f'R{len(rows)+1:03}',phase=heading,source={'start':offset,'end':offset+len(line),'quote':line}))
        elif re.match(r'^\s*\d+\s+\S',line):heading=line.strip()
        elif re.match(r'^\s*\d+[.)]',line):unparsed.append({'start':offset,'text':line})
        offset+=len(line)
    result=candidate_from_records({'source_sha256':hashlib.sha256(protocol.encode()).hexdigest(),'operations':rows})
    result['unparsed_numbered_lines']=unparsed;return result

def source_reference(*, repeat_scenario=4):
    """Reuse verified source-anchor templates, independent of question and candidate."""
    from oeq_atomic_source_projection import _locked,HOME
    _locked()
    if repeat_scenario not in (4,5):raise ValueError('Source wash range requires scenario 4 or 5')
    # Both scenarios are locked independently; the original Q13 lock covers only wash4.
    locks={4:'678590e966ce4ad2aa3a32faf6aa8bea216dbb6be1db951b01e2604d2e9dd2cd',5:'a36dda5a6513c3c1f2113ab7a383296f8536aa5c9356d31121c9eef8c0ebcb7b'}
    path=HOME/f'reference_full_wash{repeat_scenario}.json'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=locks[repeat_scenario]:raise ValueError('Source template changed')
    data=json.loads(path.read_text())
    source=(HOME/'source/idisco_dec2016_raw.txt').read_text()
    for row in data['operations']:
        anchor=row['source']
        if hashlib.sha256(source.encode()).hexdigest()!=anchor['text_sha256'] or source[anchor['start']:anchor['end']].rstrip()!=anchor['quote']:
            raise ValueError('Source occurrence anchor mismatch')
    data['operations']=annotate(data['operations'],trusted_reference_phase=True)
    return {**data,'schema_version':VERSION,'reference_selection':'iDISCO+ December 2016 source template; applicability must be separately supplied'}

SCOPE_CONTEXT_VERSION='idisco-source-sequence-scope-v1'

def contextual_scope(rows, *, method):
    """Derived scope only. An observed solvent reversal is not a completed workflow.

    The iDISCO source separates dehydration/bleach/rehydration pretreatment
    from final solvent clearing. Do not generalize this interpretation to other
    methods, infer a labeling stage, or synthesize unreported operations.
    """
    out=deepcopy(rows)
    if method!='iDISCO+':return out
    def asserted(r):
        if r.get('execution_status')!='ASSERTED_OPERATION':return False
        heading=r.get('phase','').lower();operation=r.get('operation','').lower()
        # Local scope evidence must itself be asserted. Heading modality and
        # trailing action conditions are not captured by the legacy role parser.
        # Manner qualifiers such as 'without shaking' remain ordinary execution.
        if re.search(r'\b(?:optional(?:ly)?|conditional|if needed|if desired|only if|do not|never|omit|skip)\b',heading):return False
        if re.search(r'\b(?:is|are|may be|can be)\s+optional\b|\b(?:only if|if needed|if desired|if required|when needed)\b',operation):return False
        if re.search(r'\b(?:is|are)\s+(?:not\s+(?:performed|required)|omitted|skipped)\b',operation):return False
        return True
    def concentration(r):
        if not asserted(r) or r.get('composition')!='methanol':return None
        if re.search(r'\d+(?:\.\d+)?\s*(?:[-–—]|to)\s*\d+(?:\.\d+)?\s*%',r['operation'],re.I):return None
        values=re.findall(r'(\d+(?:\.\d+)?)\s*%',r['operation'])
        return float(values[0]) if len(values)==1 else None
    for b,bleach in enumerate(out):
        if not asserted(bleach) or bleach.get('operation_role')!='bleaching':continue
        branch=bleach.get('branch','main')
        left=b-1
        while left>=0 and out[left].get('branch','main')==branch and concentration(out[left]) is not None and out[left].get('phase')==out[b-1].get('phase'):left-=1
        right=b+1
        while right<len(out) and out[right].get('branch','main')==branch and concentration(out[right]) is not None and out[right].get('phase')==out[b+1].get('phase'):right+=1
        before=out[left+1:b];after=out[b+1:right]
        if len(before)<2 or len(after)<2:continue
        up=[concentration(r) for r in before];down=[concentration(r) for r in after]
        if not (all(a<=z for a,z in zip(up,up[1:])) and up[0]<up[-1]
                and all(a>=z for a,z in zip(down,down[1:])) and down[0]>down[-1]
                and down[0]<up[-1]):continue
        segment=out[left+1:right]
        # An explicit contrary heading makes context ambiguous, not an override.
        contrary=any(re.search(r'post[- ]?(?:immuno|label)|final\s+(?:clearing|dehydration)|after\s+(?:immuno|label)',r.get('phase',''),re.I) for r in segment)
        source_rows={r['id']:r for r in source_reference()['operations']}
        source_basis=[{'reference_operation_id':key,'source':source_rows[key]['source']} for key in ('REF-p-1.01','REF-p-5.01','REF-p-6.01','REF-c-1.01')]
        evidence={'rule':SCOPE_CONTEXT_VERSION,'source_basis':source_basis,
            'interpretation':'OBSERVED_PRETREATMENT_SOLVENT_REVERSAL' if not contrary else 'CONFLICTING_EXPLICIT_FINAL_HEADING',
            'method':'iDISCO+', 'operation_ids':[r['id'] for r in segment],
            'anchors':[{'id':r['id'],'source':deepcopy(r.get('source')),'quote':r['raw_text'],'heading':r.get('phase','')} for r in segment],
            'ascending_concentrations':up,'descending_concentrations':down,
            'scope_basis':'observed ascending methanol, asserted bleaching, then observed descending methanol in one branch',
            'unreported_steps_inferred':False,'workflow_completion_inferred':False}
        for row in segment:
            if row['comparison_phase']==(UNKNOWN if contrary else 'pretreatment'):continue
            row['scope_phase_before_context']=row['comparison_phase']
            row['comparison_phase']=UNKNOWN if contrary else 'pretreatment'
            row['scope_context_evidence']=deepcopy(evidence)
    return out

def scope_coverage(result):
    """Coverage/assessability is independent of technical parse validity."""
    candidate=result['candidate']
    executed=[r for r in candidate['operations'] if execution_status(r)=='ASSERTED_OPERATION']
    unresolved=candidate['unresolved_scope_operations']
    result['candidate_scope_coverage']={
        'status':'HAS_SCOPED_OPERATIONS' if executed else 'UNRESOLVED_SCOPE' if unresolved else 'NO_ASSERTED_OPERATIONS_IN_REQUESTED_SCOPE',
        'selected_asserted_count':len(executed),'unresolved_count':len(unresolved),
        'technical_processing_status':'PROCESSABLE',
        'empty_metric_policy':'existing continuous metric convention SR=0, SP=0; not scientific certification',
        'scientific_correctness_inferred':False}
    return result

def pair_scope(candidate,reference,scope,*,method):
    if method not in {'iDISCO+','FDISCO'}:raise ValueError('Only source-verified atomic methods supported')
    if method=='FDISCO' and reference.get('source_sha256')!='35c9600df019b29483e752b96daae7276da0eab669106435b72c78722f51ac1d':raise ValueError('FDISCO source-verified reference required')
    if scope not in SCOPES:raise ValueError('Explicit scope required')
    result={'schema_version':VERSION,'scope':scope,'method':method,'official_score':False}
    for side,data in [('candidate',candidate),('reference',reference)]:
        selected=[];excluded=[];unknown=[]
        rows=contextual_scope(data['operations'],method=method) if side=='candidate' else data['operations']
        for row in rows:
            phase=row['comparison_phase']
            if phase in SCOPES[scope]:selected.append(deepcopy(row))
            elif phase==UNKNOWN:unknown.append(deepcopy(row))
            else:excluded.append(deepcopy(row))
        result[side]={'operations':selected,'excluded_operations':excluded,'unresolved_scope_operations':unknown}
        if 'occurrence_groups' in data:
            result[side]['occurrence_groups']=deepcopy(data['occurrence_groups'])
    result['scope_status']='REQUIRES_REVIEW' if any(result[s]['unresolved_scope_operations'] for s in ('candidate','reference')) else 'RESOLVED_LITERAL_SCOPE'
    changed=any('scope_context_evidence' in r for key in ('operations','excluded_operations','unresolved_scope_operations') for r in result['candidate'][key])
    if changed or not any(execution_status(r)=='ASSERTED_OPERATION' for r in result['candidate']['operations']):
        result['scope_context_version']=SCOPE_CONTEXT_VERSION
        scope_coverage(result)
    return result

def eligibility(a,b):
    reasons=[]
    if any(execution_status(r)!='ASSERTED_OPERATION' for r in (a,b)):reasons.append('nonasserted_operation')
    ap,bp=a.get('comparison_phase',UNKNOWN),b.get('comparison_phase',UNKNOWN)
    if ap!=UNKNOWN and bp!=UNKNOWN and ap!=bp:reasons.append('phase_conflict')
    ar,br=a.get('operation_role',UNKNOWN),b.get('operation_role',UNKNOWN)
    compatible=any({ar,br}<=s for s in ({'dehydration','methanol_wash'},{'ri_matching','storage'}))
    if (a.get('strict_operation_roles') or b.get('strict_operation_roles')) and {ar,br}=={'ri_matching','storage'}:compatible=False
    if ar!=UNKNOWN and br!=UNKNOWN and ar!=br and not compatible:reasons.append('role_conflict')
    if {composition(a),composition(b)}=={'dcm_methanol_mixture','dcm_without_stated_cosolvent'}:reasons.append('pure_mixed_solvent_conflict')
    return {'eligible':not reasons,'reasons':reasons,'unknown_role':UNKNOWN in (ar,br),'meaning':'eligibility_only_not_equivalence_or_correctness'}

def diagnose(pair,matrix):
    rs=pair['reference']['operations'];cs=pair['candidate']['operations']
    if len(matrix)!=len(rs) or any(len(row)!=len(cs) for row in matrix):raise ValueError('Matrix shape mismatch')
    def direction(a,b,m):
        out=[]
        for i,row in enumerate(a):
            eligible=[j for j,col in enumerate(b) if eligibility(row,col)['eligible']]
            raw=max(range(len(b)),key=lambda j:m[i][j]) if b else None
            selected=max(eligible,key=lambda j:m[i][j]) if eligible else None
            out.append({'id':row['id'],'role':row['operation_role'],'raw_partner':b[raw]['id'] if raw is not None else None,'raw_cosine':m[i][raw] if raw is not None else None,'typed_partner':b[selected]['id'] if selected is not None else None,'typed_cosine':m[i][selected] if selected is not None else None,'eligible_count':len(eligible),'raw_pair_rejection':eligibility(row,b[raw])['reasons'] if raw is not None else [],'unknown_role':row['operation_role']==UNKNOWN})
        return out
    return {'version':VERSION,'official_score_changes':False,'threshold':None,'reference':direction(rs,cs,matrix),'candidate':direction(cs,rs,list(map(list,zip(*matrix))))}

def prepare_atomic_pair(protocol, context, config):
    """Original prepare-entry opt-in sidecar. No canonical roles or answer locks required."""
    from oeq_simple_representation import from_catalog
    if config.get('version')!=VERSION:raise ValueError('Explicit automatic atomic version required')
    if set(config)-{'version','method','scope','repeat_scenario'}:raise ValueError('Unsupported atomic option')
    candidate=candidate_from_records(from_catalog(protocol,context['source_record_catalog']))
    pair=pair_scope(candidate,source_reference(repeat_scenario=config.get('repeat_scenario',4)),config['scope'],method=config['method'])
    pair['candidate']['source_sha256']=candidate['source_sha256']
    pair['applicability']='Source-operation comparison only; task/sample scientific applicability not certified'
    return pair
