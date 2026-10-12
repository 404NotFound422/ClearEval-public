"""Post-development software challenge; preserves the frozen v2 failures."""
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_step_representation_optimizer_v2 as v2
import cce_validation as core

OUT=ROOT/'artifacts/cce_validation/optimizer_20261010/step_representation_counterexamples_v1'
REG=[{'object_id':s,'aliases':[s]} for s in ['ALPHA','BETA']]
CHALLENGES=[
 ('adverb_between_coordinator_and_action','Store in ALPHA and then gently wash in ALPHA.',False),
 ('later_negated_obligation','Store in ALPHA; do not store in ALPHA.',False),
 ('lexical_unnecessary','Storage in ALPHA is unnecessary.',False),
 ('conditional_provided_that','Store in ALPHA provided that storage is permitted.',False),
]

def bind(p):return {'path':str(p),'sha256':core.filehash(p)}
def slot(s):return v2.extract_slots(v2.synthetic_unit(s),REG)

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 files=[Path(__file__),Path(v2.__file__),v2.OUT/'plan.json',v2.OUT/'summary.json',v2.OUT/'evidence_packets.json',v2.OUT/'reference_evidence_packets.json']
 before=[bind(p) for p in files]
 plan={'stage':'post_development_challenge_not_pre_registered_confirmation','frozen_inputs':before,
       'structural_challenges':CHALLENGES,'multiplicity_challenges':[(5,1),(5,4),(5,5)],
       'selection':'General software examples after v2 development; not independent semantic annotations or expert gold.',
       'new_judge_requests':0}
 core.write(OUT/'plan.json',plan)
 reference=slot('Store in ALPHA.');observations=[]
 for name,text,expected in CHALLENGES:
  answer=slot(text);actual=v2.compatible(reference,answer)
  observations.append({'probe_id':name,'reference':'Store in ALPHA.','answer':text,
      'expected_match':expected,'actual_v2_match':actual,'pass':actual==expected,'answer_slots':answer})
 repeated=slot('Incubate in ALPHA.');counts=[]
 for nr,ng in [(5,1),(5,4),(5,5)]:
  score=v2.score_slots([repeated]*nr,[repeated]*ng)
  counts.append({'reference_units':nr,'generated_distinct_units':ng,'v2_reference_coverage':score['sr'],
      'v2_generated_coverage':score['sp'],'maximum_possible_distinct_matches':min(nr,ng),
      'one_to_one_reference_coverage':min(nr,ng)/nr,'one_to_one_generated_coverage':min(nr,ng)/ng,
      'v2_many_to_one_groups':score['many_to_one_reference_groups'],'no_numeric_parameter_values_used':True})
 baselines=[]
 for p in core.read(v2.OUT/'evidence_packets.json'):
  if '__baseline__' not in p['case_id']:continue
  thf=[s for s in p['slots'] if s['obligation_keys']==[['incubate','THF']]]
  baselines.append({'case_id':p['case_id'],'question_id':p['question_id'],'distinct_incubate_THF_units':len(thf),
      'unit_ids':[s['unit_id'] for s in thf],'source_envelopes':[s['source_envelope'] for s in thf],
      'same_reference_five_incubation_units_available':len(thf)>=5})
 summary={'status':'completed_failures_preserved','structural_probes':len(observations),'failed_structural_probes':sum(not p['pass'] for p in observations),
     'multiplicity_counterexamples':2,'multiplicity_positive_control':1,'baselines_with_five_distinct_THF_units':sum(p['same_reference_five_incubation_units_available'] for p in baselines),
     'new_judge_requests':0,'original_v2_changed':False,'semantic_accuracy_validated':False,
     'interpretation':'v2 is not a complete negation/multiple-action parser; unrestricted row-max coverage does not require distinct action evidence.'}
 core.write(OUT/'structural_results.json',observations);core.write(OUT/'multiplicity_results.json',counts);core.write(OUT/'baseline_distinct_evidence.json',baselines);core.write(OUT/'summary.json',summary)
 assert before==[bind(p) for p in files]
 core.write(OUT/'verification.json',{'status':'pass','frozen_inputs_unchanged':True,'input_hashes':before,'new_judge_requests':0})
 core.write(OUT/'execution_commands.json',[{'actual_command':[sys.executable,*sys.argv],'cwd':str(ROOT),'script_sha256':core.filehash(__file__),'new_judge_requests':0}])
 (OUT/'README.md').write_text('# v2 独立软件反例检查\n\n这是开发后的挑战审计，未作为盲化语义金标准。4 个新一般语言反例均暴露 v2 的过度肯定匹配，原结果原样保存。\n\n五个相同动作对象的参考单位对一份/四份答案单位，v2 仍给 5/5 参考覆盖；一对一最大只能给 1/5 和 4/5。当前 q2/q21/q22 三个真实 baseline 各有五份分开的 THF 孵育单位，一对一可保留这些动作的真实证据数量；这仍不证明重复次数、梯度或参数正确。\n\n[反例](structural_results.json) · [计数反例](multiplicity_results.json) · [原文数量证据](baseline_distinct_evidence.json) · [核验](verification.json)\n',encoding='utf-8')
 print(json.dumps(summary))

if __name__=='__main__':main()
