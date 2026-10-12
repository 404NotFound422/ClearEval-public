"""Frozen, conservative action/object slot backend; original BioPro is unchanged.

The rule-based backend is a distinct developmental coverage diagnostic, not a
replacement cosine matcher or semantic gold standard. No model calls occur.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re
import socket
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
import cce_step_representation_optimizer_v1 as prior
import cce_validation as core

BASE = ROOT/'artifacts/cce_validation'
V1 = BASE/'optimizer_20261010/step_representation_v1'
OUT = BASE/'optimizer_20261010/step_representation_v2'
OLD = BASE/'judges/local_controls_supplement_v2'

# Morphological variants only. Transfer, incubation, immersion, equilibration,
# washing, and storage deliberately remain different classes.
ACTION_PATTERNS = {
    'incubate': r'incubat(?:e[ds]?|ing|ions?)',
    'store': r'stor(?:e[ds]?|ing|age)',
    'transfer': r'transfer(?:s|red|ring)?',
    'wash': r'wash(?:es|ed|ing)?',
    'rinse': r'rins(?:e[ds]?|ing)',
    'immerse': r'immers(?:e[ds]?|ing|ion)',
    'soak': r'soak(?:s|ed|ing)?',
    'mount': r'mount(?:s|ed|ing)?',
    'equilibrate': r'equilibrat(?:e[ds]?|ing|ion)',
    'replace': r'replac(?:e[ds]?|ing)',
    'dehydrate': r'dehydrat(?:e[ds]?|ing|ion)',
    'clear': r'clear(?:s|ed|ing)?',
    'image': r'imag(?:e[ds]?|ing)',
}
ACTION = re.compile(r'\b(?:'+'|'.join(ACTION_PATTERNS.values())+r')\b', re.I)
COORDINATOR = re.compile(r'(?:;|\.(?=\s+[A-Z])|\band\s+(?:then\s+)?|\bthen\s+)(?=\s*(?:'+ '|'.join(ACTION_PATTERNS.values())+r')\b)', re.I)
PREPOSITION = re.compile(r'\b(?:in|into|within|with|to|from|without|using)\b', re.I)
MODAL = re.compile(r'\b(?:if|unless|may|might|could|would|should|can|optional(?:ly)?|whether|either|or)\b|\?', re.I)
NEGATION = re.compile(r'\b(?:not|never|avoid|omit|without)\b', re.I)
NONREQUIRED = re.compile(r'\bnot\s+(?:required|needed|recommended|performed)\b', re.I)


def require(ok, message):
    if not ok: raise AssertionError(message)


def read(path): return core.read(path)
def save(name, obj): core.write(OUT/name, obj)
def bind(path): return {'path': str(Path(path).resolve()), 'sha256': core.filehash(path)}


def csv_write(path, rows):
    fields=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w',encoding='utf-8-sig',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=fields);writer.writeheader()
        for row in rows:
            writer.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})


def local_evidence(unit, start, end):
    """Project exact selected characters to v1 original source offsets."""
    source_chars = []
    for piece in unit['source_pieces']:
        for k, ch in enumerate(piece['text']):
            if not ch.isspace(): source_chars.append((ch, piece['start']+k))
    selected = [(k,ch) for k,ch in enumerate(unit['text']) if not ch.isspace()]
    require(''.join(c for _,c in selected)==''.join(c for c,_ in source_chars), 'unit_source_projection')
    mapping = {k:p for (k,c),(d,p) in zip(selected, source_chars)}
    positions = [mapping[k] for k in range(start,end) if k in mapping]
    return {'unit_start':start, 'unit_end':end, 'text':unit['text'][start:end],
            'source_character_offsets':positions,
            'source_start':min(positions) if positions else None,
            'source_end':max(positions)+1 if positions else None}


def action_class(surface):
    hits=[k for k,p in ACTION_PATTERNS.items() if re.fullmatch(p,surface,re.I)]
    require(len(hits)==1, 'ambiguous_action_lexicon')
    return hits[0]


def extract_slots(unit, registry):
    text=unit['text']
    # Only explicit grammatical coordinators start additional obligations.
    # Embedded purpose and participial modifiers are not invented operations.
    breaks=[];purpose_modifiers=[]
    for m in COORDINATOR.finditer(text):
        next_action=ACTION.search(text,m.end())
        preceding=text[breaks[-1] if breaks else 0:m.start()]
        # A gerund coordinated inside an explicit purpose phrase ("for ...
        # matching and clearing") is recorded as purpose, not a second order.
        if next_action and next_action.group().lower().endswith('ing') and re.search(r'\bfor\b[^.;]*$',preceding,re.I):
            purpose_modifiers.append((next_action.start(),next_action.end()));continue
        breaks.append(m.end())
    bounds=[0]+breaks+[len(text)]
    frames=[]
    for ci,(start,end) in enumerate(zip(bounds,bounds[1:])):
        clause=text[start:end]
        temporal_end=clause.find(',')+1 if re.match(r'^\s*(?:Before|After)\b',clause,re.I) and ',' in clause else 0
        candidates=list(ACTION.finditer(clause,temporal_end))
        a=next((m for m in candidates if not (
            m.group().lower() in ('cleared','dehydrated') and re.match(r'\s+(?:tissue|sample|brain|block)\b',clause[m.end():],re.I))),None)
        frame={'obligation_index':ci, 'clause_start':start, 'clause_end':end,
               'source_clause':local_evidence(unit,start,end), 'action_class':None,
               'object_id':None, 'status':'unresolved', 'reason':None,
               'parameter_values_are_not_match_keys':True, 'object_inheritance_performed':False}
        if not a:
            frame['reason']='no_explicit_action';frames.append(frame);continue
        klass=action_class(a.group());frame['action_class']=klass
        frame['action_evidence']=local_evidence(unit,start+a.start(),start+a.end())
        # A bare mention in explanatory prose is insufficient. Recognize direct
        # heads, explicit repeat operator, or an explicit passive auxiliary.
        prefix=clause[temporal_end:a.start()].strip()
        head_ok=(not prefix or re.fullmatch(r'(?:then\s+|next\s+|repeat\s+|do\s+(?:not\s+)?|avoid\s+|never\s+|optionally\s+|may\s+)*',prefix+' ',re.I)
                 or re.search(r'\b(?:is|are|was|were|be|been|being)\s*$',prefix,re.I))
        if NEGATION.search(prefix) or NONREQUIRED.search(clause):
            frame['status']='negative';frame['reason']='explicit_action_negation';frames.append(frame);continue
        if MODAL.search(clause):
            frame['reason']='conditional_modal_or_alternative_scope';frames.append(frame);continue
        if not head_ok:
            frame['reason']='action_not_explicit_clause_head';frames.append(frame);continue
        objects=[]
        for obj in registry:
            for alias in obj['aliases']:
                for m in re.finditer(r'(?<![A-Za-z0-9])'+re.escape(alias)+r'(?![A-Za-z0-9])',clause,re.I):
                    if m.start()<a.end():continue
                    preps=list(PREPOSITION.finditer(clause,a.end(),m.start()))
                    prep=preps[-1] if preps else None
                    objects.append({'object_id':obj['object_id'],'preposition':prep.group().lower() if prep else None,
                        'evidence':local_evidence(unit,start+m.start(),start+m.end()),
                        'preposition_evidence':local_evidence(unit,start+prep.start(),start+prep.end()) if prep else None})
        frame['object_mentions']=objects
        if any(o['preposition']=='without' for o in objects):
            frame['status']='negative';frame['reason']='explicit_absent_object';frames.append(frame);continue
        allowed={'to','into'} if klass=='transfer' else {'in','into','within','with','using'}
        targets=[o for o in objects if o['preposition'] in allowed]
        ids=sorted({o['object_id'] for o in targets})
        if len(ids)!=1:
            frame['reason']='object_unknown_or_unbound' if not ids else 'multiple_destination_objects';frames.append(frame);continue
        # Multiple independent operations cannot be covered by only a primary
        # action. Unsplit imperative-looking action mentions remain unresolved.
        unparsed=[]
        for extra in candidates:
            if extra.start()<=a.start():continue
            if (start+extra.start(),start+extra.end()) in purpose_modifiers:continue
            before=clause[max(a.end(),extra.start()-30):extra.start()]
            if re.search(r'\b(?:and|then)\s*$',before,re.I): unparsed.append(extra.group())
        if unparsed:
            frame['reason']='additional_operation_unresolved';frame['additional_actions']=unparsed;frames.append(frame);continue
        frame.update({'object_id':ids[0], 'status':'resolved_positive', 'reason':'explicit_head_action_and_unique_bound_object'})
        frames.append(frame)
    resolved=bool(frames) and all(f['status']=='resolved_positive' for f in frames)
    return {'unit_id':unit['unit_id'],'text':text,'source_envelope':unit['source_envelope'],
        'frames':frames, 'all_obligations_resolved_positive':resolved,
        'explicit_purpose_modifiers':[local_evidence(unit,a,b) for a,b in purpose_modifiers],
        'obligation_keys':sorted([[f['action_class'],f['object_id']] for f in frames]) if resolved else None,
        'matching_rule':'Exact full multiset of affirmative action/object obligations; no partial-unit coverage.',
        'parameter_evidence':unit.get('parameter_evidence',[]),
        'parameter_correctness_or_repetition_completeness_validated':False,
        'full_semantic_parse_validated':False}


def compatible(a,b):
    return bool(a['all_obligations_resolved_positive'] and b['all_obligations_resolved_positive']
                and a['obligation_keys']==b['obligation_keys'])


def synthetic_unit(text):
    return {'unit_id':'synthetic','text':text,'source_envelope':prior.span(text,0,len(text)),
            'source_pieces':[prior.span(text,0,len(text))], 'parameter_evidence':[]}


PROBES=[
    ('morphology','Incubate in ALPHA.','Incubation with ALPHA.',True),
    ('passive','Store in ALPHA.','The sample was stored in ALPHA.',True),
    ('wrong_object','Store in ALPHA.','Store in BETA.',False),
    ('negation','Store in ALPHA.','Do not store in ALPHA.',False),
    ('avoid','Store in ALPHA.','Avoid storing in ALPHA.',False),
    ('not_required','Store in ALPHA.','Storage in ALPHA is not required.',False),
    ('modal','Store in ALPHA.','May store in ALPHA.',False),
    ('conditional','Store in ALPHA.','If needed, store in ALPHA.',False),
    ('question','Store in ALPHA.','Store in ALPHA?',False),
    ('wrong_action','Transfer to ALPHA.','Incubate in ALPHA.',False),
    ('transfer_direction','Transfer from ALPHA to BETA.','Transfer to BETA from ALPHA.',True),
    ('reversed_direction','Transfer from ALPHA to BETA.','Transfer from BETA to ALPHA.',False),
    ('unknown_pronoun','Store in ALPHA.','Store in it.',False),
    ('ambiguous_medium','Store in ALPHA.','Store in ALPHA and BETA.',False),
    ('object_absent','Incubate in ALPHA.','Incubate without ALPHA.',False),
    ('numerical_parameter_not_step_identity','Incubate in 10% ALPHA for 2 hours.','Incubate in 90% ALPHA for 8 hours.',True),
    ('partial_multiaction_forbidden','Incubate in ALPHA and store in BETA.','Incubate in ALPHA.',False),
    ('all_multiaction_obligations','Incubate in ALPHA and store in BETA.','Incubation with ALPHA; storage in BETA.',True),
    ('reversed_order_not_correctness_score','Incubate in ALPHA and store in BETA.','Store in BETA and incubate in ALPHA.',True),
    ('embedded_negation_not_action','Store in ALPHA without shaking.','Store in ALPHA.',True),
    ('unrecognized_object','Store in ALPHA.','Store in GAMMA.',False),
    ('named_purpose_not_explicit_action','Store in ALPHA.','ALPHA is used for storage.',False),
    ('repeat_modifier_not_count_verification','Repeat incubation in ALPHA twice.','Incubate in ALPHA.',True),
]


def inputs():
    return [Path(__file__),Path(prior.__file__),Path(core.__file__),
        *[V1/n for n in ['plan.json','summary.json','evidence_packets.json','reference_evidence_packets.json','per_case.json','paired_results.json']],
        *[OLD/n for n in ['cases.json','pairs.json','references.json','step_results.json']]]


def command_record(command,**extra):
    p=OUT/'execution_commands.json';rows=read(p) if p.exists() else []
    rows.append({'utc':prior.judges.now(),'actual_command':[sys.executable,*sys.argv], 'cwd':str(ROOT),
        'script_sha256':core.filehash(__file__), 'command':command,'new_judge_requests':0,**extra});core.write(p,rows)


def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    policy={'version':'exact_action_object_full_obligation_multiset_v2',
        'population':'Original 21 development texts / 15 pairs, no subset selected by results.',
        'action_patterns':ACTION_PATTERNS,'coordinator_regex':COORDINATOR.pattern,
        'object_registry':read(V1/'plan.json')['policy']['object_registry'],
        'action_identity':'Morphological only. Transfer is not incubation, immersion, or equilibration.',
        'binding':'Explicit local head and preposition-bound object. Transfer destination excludes from-object. No cross-unit implicit inheritance.',
        'ambiguity':'Negated, conditional, modal, unknown and multiply bound objects remain not positively matched, with status and counts separate.',
        'multi_action':'Exact full multiset of all explicit coordinated obligations, never a partial primary-action hit. Unknown additional operations remain unresolved.',
        'denominators':'Original surface unit counts retained. Symbolic SR/SP are positive-coverage lower bounds with unresolved counts, not semantic error rates.',
        'numeric_parameters':'Concentration, time, temperature, repeat counts excluded from identity; retained as evidence. A match does not establish parameter/repetition correctness.',
        'known_many_to_one_limit':'Repeated same action/object reference units can all match one generated unit under unchanged row/column coverage. Gradient/repetition completion not established.',
        'baseline':'Original BioProBench and v1 numeric results retained separately, never overwritten.',
        'threshold':'Symbolic backend has no tunable cosine threshold. Baseline .6/.7/.8 only for contextual comparison.',
        'new_judge_requests':0,'formal_eligible':False,'expert_returns':0}
    plan={'created_utc':prior.judges.now(),'policy':policy,'synthetic_probes':[dict(zip(['probe_id','reference','answer','expected'],p)) for p in PROBES],
        'frozen_inputs':[bind(p) for p in inputs()], 'expected_development_observation_not_acceptance_target':
        'Explicit store+DBE is present in the three original baselines and absent after deletion; transfer-vs-incubation mismatch intentionally persists.'}
    if (OUT/'plan.json').exists():
        old=read(OUT/'plan.json');require(old['policy']==policy and old['frozen_inputs']==plan['frozen_inputs'],'frozen_v2_changed_use_new_version')
    else:save('plan.json',plan)
    command_record('prepare',status='frozen_before_probes_and_scoring')
    print(json.dumps({'status':'prepared','probes':len(PROBES),'new_judge_requests':0}))


def validate_plan():
    plan=read(OUT/'plan.json')
    for item in plan['frozen_inputs']:require(core.filehash(item['path'])==item['sha256'],'frozen_input_drift:'+item['path'])
    return plan


def probes():
    plan=validate_plan();registry=[{'object_id':s,'aliases':[s]} for s in ['ALPHA','BETA']];results=[]
    for p in plan['synthetic_probes']:
        a=extract_slots(synthetic_unit(p['reference']),registry);b=extract_slots(synthetic_unit(p['answer']),registry)
        actual=compatible(a,b)
        results.append({**p,'actual':actual,'pass':actual==p['expected'],'reference_slots':a,'answer_slots':b})
    save('synthetic_probe_results.json',results)
    summary={'status':'pass' if all(p['pass'] for p in results) else 'fail','probes':len(results),'passed':sum(p['pass'] for p in results),
        'new_judge_requests':0,'semantic_accuracy_validated':False,'plan_sha256':core.filehash(OUT/'plan.json')}
    save('synthetic_probe_summary.json',summary);command_record('probes',**summary);print(json.dumps(summary))
    require(summary['status']=='pass','synthetic_probe_failure_no_data_run')


def score_slots(ref,gen):
    matrix=[[compatible(r,g) for g in gen] for r in ref]
    rh=[any(row) for row in matrix];gh=[any(row[k] for row in matrix) for k in range(len(gen))]
    return {'sr':sum(rh)/len(ref) if ref else None,'sp':sum(gh)/len(gen) if gen else None,
        'reference_n':len(ref),'generated_n':len(gen),'reference_hits':sum(rh),'generated_hits':sum(gh),
        'reference_unresolved_n':sum(not x['all_obligations_resolved_positive'] for x in ref),
        'generated_unresolved_n':sum(not x['all_obligations_resolved_positive'] for x in gen),
        'matrix':matrix,'reference_positive_hits':rh,'generated_positive_hits':gh,
        'many_to_one_reference_groups':[[i for i,r in enumerate(matrix) if r[k]] for k in range(len(gen)) if sum(r[k] for r in matrix)>1]}


def run():
    socket.create_connection=prior.no_network;socket.socket.connect=prior.no_network;socket.socket.connect_ex=prior.no_network
    plan=validate_plan();require(read(OUT/'synthetic_probe_summary.json')['status']=='pass','probes_not_passed')
    cases=read(OLD/'cases.json')['cases'];pairs=read(OLD/'pairs.json');refs=read(OLD/'references.json')['references']
    require(len(cases)==21 and len(pairs)==15,'population_drift')
    old={p['case_id']:p for p in read(V1/'evidence_packets.json')}
    oldsteps={p['case_id']:p['step_result'] for p in read(OLD/'step_results.json')}
    registry=plan['policy']['object_registry'];refpack=[];refslots={}
    for p in read(V1/'reference_evidence_packets.json'):
        slots=[extract_slots(u,registry) for u in p['units']]
        refslots[p['source_id']]=slots;refpack.append({'source_id':p['source_id'],'reference_provenance':bind(V1/'reference_evidence_packets.json'),'slots':slots})
    results=[];packets=[]
    original={p['case_id']:p for p in read(V1/'per_case.json') if p['mode']=='original_biopro_baseline' and p['threshold']==.7}
    for case in cases:
        cid=case['case_id'];text=case['model_response'];segments=core.segment(text)
        require(segments==oldsteps[cid]['generated_steps'],'original_core_segment_drift')
        rep=prior.representation(text,segments,registry,cid)
        require(rep['units']==old[cid]['units'],'full_text_reparse_unit_drift')
        slots=[extract_slots(u,registry) for u in rep['units']];refid=old[cid]['reference_id'];s=score_slots(refslots[refid],slots)
        results.append({'case_id':cid,'question_id':case['question_id'],'condition':case['condition'],'answer_sha256':core.digest(text),
            'backend':'exact_action_object_full_obligation_multiset_v2','reference_id':refid,**s,
            'original_biopro_at_0_7':{'sr':original[cid]['sr'],'sp':original[cid]['sp']},
            'source_full_text_reparsed':True,'formal_eligible':False,'semantic_accuracy_validated':False})
        packets.append({'case_id':cid,'question_id':case['question_id'],'answer_sha256':core.digest(text),
            'original_source':bind(OLD/'cases.json'),'original_case_json_pointer':f"/cases/{cases.index(case)}/model_response",'slots':slots})
    byid={r['case_id']:r for r in results};paired=[]
    for p in pairs:
        a,b=byid[p['baseline_case_id']],byid[p['variant_case_id']]
        paired.append({**p,'backend':'exact_action_object_full_obligation_multiset_v2','baseline_sr':a['sr'],'variant_sr':b['sr'],
            'delta_sr':b['sr']-a['sr'],'baseline_sp':a['sp'],'variant_sp':b['sp'],'delta_sp':b['sp']-a['sp'],
            'baseline_n':a['generated_n'],'variant_n':b['generated_n'],'reference_n':a['reference_n'],
            'same_configuration_and_reference':a['reference_id']==b['reference_id'], 'both_full_texts_reparsed':True})
    condition=[]
    for name in sorted({p['condition'] for p in paired}):
        group=[p for p in paired if p['condition']==name]
        condition.append({'condition':name,'pairs':len(group),**{f'{m}_{direction}':sum((p[f'delta_{m}']<-1e-12 if direction=='negative' else p[f'delta_{m}']>1e-12 if direction=='positive' else abs(p[f'delta_{m}'])<=1e-12) for p in group) for m in ['sr','sp'] for direction in ['negative','zero','positive']}})
    statuses=Counter(f['status'] for p in packets for s in p['slots'] for f in s['frames'])
    reasons=Counter(f['reason'] for p in packets for s in p['slots'] for f in s['frames'])
    summary={'status':'completed_offline_development_candidate','cases':21,'pairs':15,'backend':'exact_action_object_full_obligation_multiset_v2',
        'condition_results':condition,'answer_units':sum(len(p['slots']) for p in packets),'frame_status_counts':dict(statuses),'frame_reason_counts':dict(reasons),
        'reference_units':sum(len(p['slots']) for p in refpack),'unresolved_answer_units':sum(r['generated_unresolved_n'] for r in results),
        'cases_with_many_to_one_reference_hits':sum(bool(r['many_to_one_reference_groups']) for r in results),
        'new_judge_requests':0,'new_local_embeddings':0,'reused_embeddings':0,'baseline_scores_exactly_reused':21,
        'original_full_texts_reparsed':21,'new_direct_scores':0,'formal_eligible':False,'expert_returns':0,
        'claim_boundary':'Exact source-supported lexical slot coverage only; not full protocol correctness, repetition completion, semantic parsing accuracy, or a replacement BioProBench score.'}
    save('evidence_packets.json',packets);save('reference_evidence_packets.json',refpack);save('per_case.json',results);save('paired_results.json',paired);save('summary.json',summary)
    csv_write(OUT/'per_case.csv',[{k:v for k,v in r.items() if k not in ['matrix','reference_positive_hits','generated_positive_hits','many_to_one_reference_groups','original_biopro_at_0_7']} for r in results])
    csv_write(OUT/'paired_results.csv',paired);csv_write(OUT/'condition_summary.csv',condition)
    validate_plan()
    save('verification.json',{'status':'pass','source_hashes_unchanged':True,'original_core_segments_reproduced':21,'v1_units_exactly_reproduced':21,
        'all_pairs_reparsed_same_configuration':all(p['same_configuration_and_reference'] for p in paired),'new_judge_requests':0,
        'semantic_accuracy_validated':False,'output_hashes':{n:core.filehash(OUT/n) for n in ['evidence_packets.json','reference_evidence_packets.json','per_case.json','paired_results.json','summary.json']}})
    lines=['# 明确动作和对象的符号覆盖候选 v2','','固定原 21 全文和 15 对。原 BioProBench 数值并列保留；新 backend 使用有来源跨度的动作词形与明确局部对象，未调整余弦阈值。',
        '','仅当整单位全部显式动作义务均为肯定、对象唯一且完整多重集合一致时匹配；否定、条件、未知对象和多对象歧义不自动当作肯定匹配。transfer 与 incubation 不合并。未匹配未决项单列，不能解释为科学错误。',
        '','| 控制 | SR 下降/不变/上升 | SP 下降/不变/上升 |','|---|---:|---:|']
    lines += [f"| {r['condition']} | {r['sr_negative']}/{r['sr_zero']}/{r['sr_positive']} | {r['sp_negative']}/{r['sp_zero']}/{r['sp_positive']} |" for r in condition]
    lines += ['', '浓度、时长、温度和重复次数均不决定动作对象身份，因此匹配不证明这些参数正确或重复次数完整。原 row/column coverage 的多对一局限保留：一个同类动作可能覆盖多个同类参考行，不能据此声称完整梯度流程均被执行。',
        '', '来源仅为冻结参考重建文本与公开开发答案；原论文来源仍沿 v1 证据链。0 judge、0 embedding、未读取人审留出或自动确认集。',
        '', '[规则](plan.json) · [一般探针](synthetic_probe_results.json) · [逐答案](per_case.csv) · [配对](paired_results.csv) · [来源槽位](evidence_packets.json) · [核验](verification.json)']
    (OUT/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    command_record('run',status=summary['status'],actual_answers=21,actual_pairs=15)
    print(json.dumps(summary))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['prepare','probes','run']);args=parser.parse_args()
    {'prepare':prepare,'probes':probes,'run':run}[args.command]()
