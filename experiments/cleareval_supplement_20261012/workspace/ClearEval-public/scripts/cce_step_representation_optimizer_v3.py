"""Distinct-evidence and sequence coverage supplement, never original BioPro SR.

Conservative unresolved guards are a separate factor from one-to-one matching.
Every mode and both denominators remain available, including frozen v2 failures.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import socket
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_validation as core
import cce_step_representation_optimizer_v1 as v1
import cce_step_representation_optimizer_v2 as v2

BASE=ROOT/'artifacts/cce_validation'
OUT=BASE/'optimizer_20261010/step_representation_v3'
AUDIT=BASE/'optimizer_20261010/step_representation_counterexamples_v1'
MODES=['frozen_v2_rowmax','guarded_rowmax','guarded_one_to_one','guarded_monotonic_one_to_one']
NEGATIVE_CUE=re.compile(r"\b(?:unnecessary|unneeded|prohibited|forbidden|contraindicated)\b|\b(?:no\s+need\s+to|need\s+not|must\s+not|do\s+not|never|avoid)\b|\b(?:don't|doesn't|isn't|aren't|wasn't|weren't)\b",re.I)
CONDITIONAL_CUE=re.compile(r'\b(?:provided\s+that|on\s+condition\s+that|in\s+case|assuming\s+that|whenever|only\s+if)\b',re.I)
UNPARSED_COORDINATOR=re.compile(r'(?:;|\band\b|\bthen\b)\s*(?:(?:then|also|do|not|never|[A-Za-z]+ly)\s+)*$',re.I)
EXTRA_PROBES=[
 ('adverb_coordinated_unresolved','Store in ALPHA.','Store in ALPHA and then gently wash in ALPHA.',False),
 ('later_negated_obligation_unresolved','Store in ALPHA.','Store in ALPHA; do not store in ALPHA.',False),
 ('unnecessary_unresolved','Store in ALPHA.','Storage in ALPHA is unnecessary.',False),
 ('provided_that_unresolved','Store in ALPHA.','Store in ALPHA provided that storage is permitted.',False),
 ('forbidden_unresolved','Store in ALPHA.','Storage in ALPHA is forbidden.',False),
 ('later_extra_same_object_unresolved','Incubate in ALPHA.','Incubate in ALPHA and carefully store in ALPHA.',False),
 ('two_obligations_cannot_be_partial','Store in ALPHA and wash in BETA.','Store in ALPHA.',False),
 ('two_obligations_both_explicit','Store in ALPHA and wash in BETA.','Storage in ALPHA; wash in BETA.',True),
]

def require(ok,msg):
 if not ok:raise AssertionError(msg)
def bind(path):return {'path':str(Path(path).resolve()),'sha256':core.filehash(path)}
def read(path):return core.read(path)
def save(name,obj):core.write(OUT/name,obj)

def guarded_slots(unit,registry):
 slot=v2.extract_slots(unit,registry);guard=[]
 for kind,regex in [('negative_scope',NEGATIVE_CUE),('conditional_scope',CONDITIONAL_CUE)]:
  for m in regex.finditer(unit['text']):
   guard.append({'kind':kind,'evidence':v2.local_evidence(unit,m.start(),m.end())})
 claimed={(f.get('action_evidence',{}).get('unit_start'),f.get('action_evidence',{}).get('unit_end')) for f in slot['frames']}
 purpose={(p['unit_start'],p['unit_end']) for p in slot['explicit_purpose_modifiers']}
 for m in v2.ACTION.finditer(unit['text']):
  if (m.start(),m.end()) in claimed|purpose:continue
  previous=unit['text'][:m.start()]
  c=UNPARSED_COORDINATOR.search(previous)
  if c:
   guard.append({'kind':'additional_coordinated_action_unresolved',
     'evidence':v2.local_evidence(unit,c.start(),m.end())})
 slot['v3_guard_evidence']=guard
 slot['v2_full_obligation_keys_before_guard']=slot['obligation_keys']
 if guard:
  slot['all_obligations_resolved_positive']=False;slot['obligation_keys']=None
  slot['unit_status']='unresolved_after_conservative_scope_guard'
 else:
  slot['unit_status']='resolved_positive' if slot['all_obligations_resolved_positive'] else 'unresolved_from_v2'
 slot['new_semantic_gold_claim']=False
 return slot

def match_matrix(ref,gen):return [[v2.compatible(r,g) for g in gen] for r in ref]

def maximum_one_to_one(matrix):
 """Exact maximum cardinality via deterministic augmenting paths."""
 owners={}
 def visit(i,seen):
  for j,yes in enumerate(matrix[i]):
   if not yes or j in seen:continue
   seen.add(j)
   if j not in owners or visit(owners[j],seen):owners[j]=i;return True
  return False
 for i in range(len(matrix)):visit(i,set())
 return sorted([[i,j] for j,i in owners.items()])

def monotonic_one_to_one(matrix):
 """LCS over compatible units; input/source order only, not causal order."""
 nr=len(matrix);ng=len(matrix[0]) if nr else 0
 dp=[[0]*(ng+1) for _ in range(nr+1)]
 for i in range(nr-1,-1,-1):
  for j in range(ng-1,-1,-1):
   dp[i][j]=max(dp[i+1][j],dp[i][j+1],1+dp[i+1][j+1] if matrix[i][j] else 0)
 pairs=[];i=j=0
 while i<nr and j<ng:
  if matrix[i][j] and 1+dp[i+1][j+1]==dp[i][j]:pairs.append([i,j]);i+=1;j+=1
  elif dp[i][j+1]>=dp[i+1][j]:j+=1
  else:i+=1
 return pairs

def coverage(ref,gen,mode):
 matrix=match_matrix(ref,gen);nr=len(ref);ng=len(gen)
 if mode.endswith('rowmax'):
  rh=[i for i,r in enumerate(matrix) if any(r)];gh=[j for j in range(ng) if any(r[j] for r in matrix)]
  assignment=None
 else:
  assignment=monotonic_one_to_one(matrix) if 'monotonic' in mode else maximum_one_to_one(matrix)
  rh=[i for i,j in assignment];gh=[j for i,j in assignment]
  require(len(rh)==len(set(rh)) and len(gh)==len(set(gh)),'duplicate_action_evidence_consumption')
  require(all(matrix[i][j] for i,j in assignment),'ineligible_assignment')
  if 'monotonic' in mode:require(all(a[0]<b[0] and a[1]<b[1] for a,b in zip(assignment,assignment[1:])),'nonmonotonic_assignment')
 return {'reference_coverage':len(rh)/nr if nr else None,'generated_coverage':len(gh)/ng if ng else None,
   'reference_n':nr,'generated_n':ng,'matched_reference_n':len(rh),'matched_generated_n':len(gh),
   'reference_unresolved_n':sum(not r['all_obligations_resolved_positive'] for r in ref),
   'generated_unresolved_n':sum(not g['all_obligations_resolved_positive'] for g in gen),
   'assignment':assignment,'matched_reference_indices':rh,'matched_generated_indices':gh,'matrix':matrix,
   'metric_kind':'Original v2 unrestricted lexical coverage' if mode=='frozen_v2_rowmax' else 'New coverage supplement, not original BioProBench SR/SP',
   'semantic_order_accuracy_validated':False}

def inputs():
 return [Path(__file__),Path(v2.__file__),Path(v1.__file__),Path(core.__file__),
   *[v2.OUT/n for n in ['plan.json','summary.json','evidence_packets.json','reference_evidence_packets.json','per_case.json','paired_results.json']],
   *[v1.OUT/n for n in ['plan.json','evidence_packets.json','reference_evidence_packets.json','per_case.json']],
   *[v2.OLD/n for n in ['cases.json','pairs.json','step_results.json']],AUDIT/'summary.json',AUDIT/'structural_results.json']

def command(command,**extra):
 p=OUT/'execution_commands.json';rows=read(p) if p.exists() else []
 rows.append({'utc':v1.judges.now(),'actual_command':[sys.executable,*sys.argv],'cwd':str(ROOT),'script_sha256':core.filehash(__file__),
      'command':command,'new_judge_requests':0,**extra});core.write(p,rows)

def prepare():
 OUT.mkdir(parents=True,exist_ok=True)
 policy={'version':'v3_guarded_distinct_and_monotonic_coverage_supplements','modes':MODES,
   'population':'All 21 original exposed control texts and 15 pairs; no holdout/confirmation.',
   'lexical_identity':'Frozen v2 morphological action/object identity; no numeric parameter values used.',
   'guard_regexes':{'negative':NEGATIVE_CUE.pattern,'conditional':CONDITIONAL_CUE.pattern,'unparsed_coordinator':UNPARSED_COORDINATOR.pattern},
   'uncertainty':'New scope cues suppress affirmative claims, retain all denominator units and explicit reason/span; no claim unresolved = scientifically wrong.',
   'one_to_one':'Maximum-cardinality bipartite matching, at most one distinct original unit per reference unit and vice versa; deterministic ascending augmenting paths.',
   'monotonic':'LCS compatible-unit alignment. Max cardinality, match-first then skip-generated-first tie. Represents source text order only.',
   'multi_action':'Each unit must resolve all explicit coordinated obligations; match complete obligation multiset. No partial-unit hit.',
   'denominators':'Same surface-unit N and M as v1/v2. Compound reference repetition remains one original unit; no expansion of numeric repeat counts.',
   'score_boundary':'One-to-one and monotonic coverage are supplements with changed assignment rule, not original BioProBench SR/SP or direct Correctness.',
   'acceptance':'Software invariants and fixed generic probes. Three store-deletion responses are developmental observations, not rule-selection targets.',
   'known_limits':['Limited literal object registry','Conservative unknowns lower observable coverage','No complete semantic grammar','No repeat-count correctness','Text order not experimental causality'],
   'new_judge_requests':0,'formal_eligible':False,'expert_returns':0}
 plan={'created_utc':v1.judges.now(),'policy':policy,'frozen_inputs':[bind(p) for p in inputs()],
   'pair_probes':[dict(zip(['probe_id','reference','answer','expected'],p)) for p in v2.PROBES+EXTRA_PROBES],
   'assignment_probes':[
     {'probe_id':'five_reference_one_evidence','reference':['A']*5,'generated':['A'],'rowmax':5,'one_to_one':1,'monotonic':1},
     {'probe_id':'five_reference_four_evidence','reference':['A']*5,'generated':['A']*4,'rowmax':5,'one_to_one':4,'monotonic':4},
     {'probe_id':'five_reference_five_evidence','reference':['A']*5,'generated':['A']*5,'rowmax':5,'one_to_one':5,'monotonic':5},
     {'probe_id':'source_order_reversal','reference':['A','B'],'generated':['B','A'],'rowmax':2,'one_to_one':2,'monotonic':1},
     {'probe_id':'same_order_with_unknown_gap','reference':['A','B'],'generated':['A','X','B'],'rowmax':2,'one_to_one':2,'monotonic':2},
     {'probe_id':'all_incompatible','reference':['A','B'],'generated':['X','X'],'rowmax':0,'one_to_one':0,'monotonic':0},
   ]}
 if (OUT/'plan.json').exists():
  old=read(OUT/'plan.json');require(old['policy']==policy and old['frozen_inputs']==plan['frozen_inputs'],'frozen_v3_changed_use_new_version')
 else:save('plan.json',plan)
 command('prepare',status='frozen_before_probes_and_scoring');print(json.dumps({'status':'prepared','pair_probes':len(plan['pair_probes']),'assignment_probes':6}))

def validate():
 plan=read(OUT/'plan.json')
 for p in plan['frozen_inputs']:require(core.filehash(p['path'])==p['sha256'],'frozen_input_drift:'+p['path'])
 return plan

def probes():
 plan=validate();reg=[{'object_id':x,'aliases':[x]} for x in ['ALPHA','BETA']];results=[]
 for p in plan['pair_probes']:
  a=guarded_slots(v2.synthetic_unit(p['reference']),reg);b=guarded_slots(v2.synthetic_unit(p['answer']),reg)
  actual=v2.compatible(a,b);results.append({**p,'actual':actual,'pass':actual==p['expected'],'reference_slots':a,'answer_slots':b})
 assignments=[]
 for p in plan['assignment_probes']:
  matrix=[[a==b for b in p['generated']] for a in p['reference']]
  one=maximum_one_to_one(matrix);seq=monotonic_one_to_one(matrix);row=sum(any(r) for r in matrix)
  actual={'rowmax':row,'one_to_one':len(one),'monotonic':len(seq)}
  assignments.append({**p,'actual':actual,'pass':all(actual[k]==p[k] for k in actual),'matrix':matrix,'one_to_one_assignment':one,'monotonic_assignment':seq})
 summary={'status':'pass' if all(r['pass'] for r in results+assignments) else 'fail','pair_probes':len(results),'pair_passed':sum(p['pass'] for p in results),
   'assignment_probes':len(assignments),'assignment_passed':sum(p['pass'] for p in assignments),'new_judge_requests':0,'plan_sha256':core.filehash(OUT/'plan.json'),
   'semantic_accuracy_validated':False}
 save('synthetic_probe_results.json',results);save('assignment_probe_results.json',assignments);save('synthetic_probe_summary.json',summary)
 command('probes',**summary);print(json.dumps(summary));require(summary['status']=='pass','probe_failure_no_real_data_run')

def run():
 socket.create_connection=v1.no_network;socket.socket.connect=v1.no_network;socket.socket.connect_ex=v1.no_network
 plan=validate();require(read(OUT/'synthetic_probe_summary.json')['status']=='pass','probes_not_passed')
 cases=read(v2.OLD/'cases.json')['cases'];pairs=read(v2.OLD/'pairs.json');registry=read(v1.OUT/'plan.json')['policy']['object_registry']
 original={p['case_id']:p for p in read(v1.OUT/'evidence_packets.json')};oldsteps={p['case_id']:p['step_result'] for p in read(v2.OLD/'step_results.json')}
 frozen={p['case_id']:p for p in read(v2.OUT/'per_case.json')};oldpack={p['case_id']:p for p in read(v2.OUT/'evidence_packets.json')}
 rawrefs=read(v1.OUT/'reference_evidence_packets.json');oldrefs={p['source_id']:p['slots'] for p in read(v2.OUT/'reference_evidence_packets.json')}
 refpack=[{'reference_id':p['source_id'],'source_binding':bind(v1.OUT/'reference_evidence_packets.json'),'slots':[guarded_slots(u,registry) for u in p['units']]} for p in rawrefs]
 refs={p['reference_id']:p['slots'] for p in refpack};packets=[];rows=[]
 require(len(cases)==21 and len(pairs)==15,'population_changed')
 for c in cases:
  cid=c['case_id'];text=c['model_response'];segments=core.segment(text);require(segments==oldsteps[cid]['generated_steps'],'core_segments_changed')
  rep=v1.representation(text,segments,registry,cid);require(rep['units']==original[cid]['units'],'surface_units_changed')
  slots=[guarded_slots(u,registry) for u in rep['units']];refid=frozen[cid]['reference_id']
  packets.append({'case_id':cid,'question_id':c['question_id'],'source_file':bind(v2.OLD/'cases.json'),
    'source_json_pointer':f"/cases/{cases.index(c)}/model_response",'answer_sha256':core.digest(text),'slots':slots})
  for mode in MODES:
   r,g=(oldrefs[refid],oldpack[cid]['slots']) if mode=='frozen_v2_rowmax' else (refs[refid],slots)
   value=coverage(r,g,mode)
   if mode=='frozen_v2_rowmax':require(value['reference_coverage']==frozen[cid]['sr'] and value['generated_coverage']==frozen[cid]['sp'],'frozen_v2_not_reproduced')
   rows.append({'case_id':cid,'question_id':c['question_id'],'condition':c['condition'],'mode':mode,'reference_id':refid,**value,
       'original_biopro_at_0_7':frozen[cid]['original_biopro_at_0_7'],'new_direct_scores':None,'formal_eligible':False})
 lookup={(r['case_id'],r['mode']):r for r in rows};paired=[]
 for p in pairs:
  for mode in MODES:
   a,b=lookup[p['baseline_case_id'],mode],lookup[p['variant_case_id'],mode]
   paired.append({**p,'mode':mode,'baseline_reference_coverage':a['reference_coverage'],'variant_reference_coverage':b['reference_coverage'],
    'delta_reference_coverage':b['reference_coverage']-a['reference_coverage'],'baseline_generated_coverage':a['generated_coverage'],
    'variant_generated_coverage':b['generated_coverage'],'delta_generated_coverage':b['generated_coverage']-a['generated_coverage'],
    'reference_n':a['reference_n'],'baseline_generated_n':a['generated_n'],'variant_generated_n':b['generated_n'],
    'same_configuration_and_reference':a['reference_id']==b['reference_id'],'both_full_texts_reparsed':True})
 conditions=[]
 for mode in MODES:
  for name in sorted({p['condition'] for p in pairs}):
   group=[p for p in paired if p['condition']==name and p['mode']==mode]
   conditions.append({'mode':mode,'condition':name,'pairs':len(group),**{f'{axis}_{direction}':sum((p[f'delta_{axis}_coverage']<-1e-12 if direction=='negative' else p[f'delta_{axis}_coverage']>1e-12 if direction=='positive' else abs(p[f'delta_{axis}_coverage'])<=1e-12) for p in group) for axis in ['reference','generated'] for direction in ['negative','zero','positive']}})
 summary={'status':'completed_offline_development_supplement','cases':21,'pairs':15,'modes':MODES,'per_case_rows':len(rows),'paired_rows':len(paired),
   'condition_results':conditions,'answer_units':sum(len(p['slots']) for p in packets),
   'guarded_unresolved_units':sum(not s['all_obligations_resolved_positive'] for p in packets for s in p['slots']),
   'units_newly_suppressed_by_guard':sum(bool(s['v3_guard_evidence']) and s['v2_full_obligation_keys_before_guard'] is not None for p in packets for s in p['slots']),
   'original_full_texts_reparsed':21,'frozen_v2_scores_reproduced':21,'new_judge_requests':0,'new_local_embeddings':0,'new_direct_scores':0,
   'formal_eligible':False,'expert_returns':0,'semantic_accuracy_validated':False,
   'claim_boundary':'Distinct source-unit evidence and textual order coverage only. Not corrected original SR, scientific order accuracy, parameter/repeat completeness, or expert validation.'}
 save('evidence_packets.json',packets);save('reference_evidence_packets.json',refpack);save('per_case.json',rows);save('paired_results.json',paired);save('summary.json',summary)
 v2.csv_write(OUT/'per_case.csv',[{k:v for k,v in r.items() if k not in ['matrix','assignment','matched_reference_indices','matched_generated_indices','original_biopro_at_0_7']} for r in rows])
 v2.csv_write(OUT/'paired_results.csv',paired);v2.csv_write(OUT/'condition_summary.csv',conditions)
 validate();save('verification.json',{'status':'pass','original_core_segments_reproduced':21,'original_v1_units_reproduced':21,'frozen_v2_rowmax_reproduced':21,
   'no_evidence_reused_in_one_to_one':True,'monotonic_assignments_checked':True,'new_judge_requests':0,
   'output_hashes':{n:core.filehash(OUT/n) for n in ['summary.json','per_case.json','paired_results.json','evidence_packets.json','reference_evidence_packets.json']}})
 lines=['# 独立动作证据与文本顺序覆盖 v3','','保留原 BioProBench 和 v2；新增保守未决标记、一对一分配及单调一对一分配。后两种覆盖改变分配规则，是补充诊断，不能冒充原 SR/SP。原 21 全文和 15 对全部重新解析，0 judge、0 embedding。',
  '','| 模式 | 控制 | 参考覆盖下降/不变/上升 | 答案覆盖下降/不变/上升 |','|---|---|---:|---:|']
 lines += [f"| {r['mode']} | {r['condition']} | {r['reference_negative']}/{r['reference_zero']}/{r['reference_positive']} | {r['generated_negative']}/{r['generated_zero']}/{r['generated_positive']} |" for r in conditions]
 lines += ['','每个独立来源单位最多消费一次；参考中的复合重复命令仍是原来一个单位，没有按照数字补造动作。参数值不参与匹配，匹配不证明梯度、次数或参数正确。单调约束只衡量与参考文本序列一致性，不能自动转成实验因果顺序或原 co_order 分。',
  '', '23 个旧探针、8 个新语言探针和 6 个分配探针先于真实重算冻结。新语言守卫保守地保留未决与原因；未决单位始终留在分母中，不把少匹配写成准确率提升。',
  '', '[规则](plan.json) · [软件探针](synthetic_probe_results.json) · [分配反例](assignment_probe_results.json) · [逐答案](per_case.csv) · [15 对](paired_results.csv) · [来源证据](evidence_packets.json) · [核验](verification.json)']
 (OUT/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');command('run',status=summary['status'],cases=21,pairs=15)
 print(json.dumps(summary))

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('command',choices=['prepare','probes','run']);args=parser.parse_args()
 {'prepare':prepare,'probes':probes,'run':run}[args.command]()
