"""Metadata-only round-two manuscript snapshots; never invoke evaluators.

Default: completed v8/v9 development; v10 is opt-in after its frozen fact audit.
Future phases require explicit --completed-stage KIND=directory and complete
original summary/verification. No source, raw, trial, ledger, or sealed reads.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/cce_validation/optimizer_round2_20261010'
OUT = BASE / 'manuscript_report_v1'
OLD = ROOT / 'artifacts/cce_validation/optimizer_20261010/step_representation_v3'
DIRECT = ['c_param', 'co_order', 'co_method', 'co_param', 'co_chem']
EGES = ['s_method', 's_label', 's_trans', 's_time']
METRICS = [*DIRECT, *EGES, 'sr', 'sp', 'Com', 'Cor', 'Eff', 'IA', 'HV']
ALLOWED = {'completion_summary.json', 'analysis_verification.json', 'per_answer.json', 'observations.json',
    'summary.json', 'inventory_verification.json', 'freeze.json', 'plan.json', 'expected_contract.json',
    'actual_commands.json', 'verification.json', 'independent_review.json', 'per_pair.json'}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def bind(p):
    return {'path': str(Path(p).resolve()), 'sha256': sha(p)}


def finite(v):
    return type(v) in (int, float) and math.isfinite(v)


def save(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf8')


class Metadata:
    def __init__(self):
        self.bindings = {}

    def load(self, p):
        p = Path(p).resolve()
        require((p.is_relative_to(BASE) or p.is_relative_to(OLD)) and p.name in ALLOWED,
                'NOT_ALLOWLISTED_PUBLIC_METADATA')
        require(not any(x.lower() in {'run', 'sealed', 'source_documents', 'prompts', 'schemas',
            'human_review', 'identity_key'} for x in p.parts), 'PROTECTED_INPUT_FORBIDDEN')
        raw = p.read_bytes(); value = json.loads(raw.decode('utf-8-sig'))
        self.bindings[str(p)] = {'path': str(p), 'sha256': hashlib.sha256(raw).hexdigest()}
        return value


def metrics_of(row):
    m = row['metrics']
    require(set(m) == set(METRICS), 'METRIC_SCHEMA_CHANGED')
    require(all(v is None or finite(v) for v in m.values()), 'NONFINITE_OR_NONNUMERIC_VALUE')
    return m


def validate_observations(summary, verification, rows, n):
    require(summary['status'] == 'experiment_complete_not_scientific_validation'
        and summary['planned_observations'] == summary['actual_observations'] == n
        and summary['pending'] == 0, 'NOT_ALL_TERMINAL')
    require(verification['status'] == 'pass' and verification['terminal_observations'] == n
        and (verification.get('all_five_terminal') is True or verification.get('all_planned_terminal') is True),
        'ORIGINAL_ANALYSIS_VERIFICATION_REQUIRED')
    require(len(rows) == n and len({r['trial_id'] for r in rows}) == n
        and all(r['status'] in ['success', 'failed'] for r in rows), 'FIXED_OBSERVATION_DENOMINATOR')
    require(sum(r['status'] == 'success' for r in rows) == summary['technical_successes']
        and summary['technical_successes'] + summary['technical_failures'] == n, 'TECHNICAL_COUNT_MISMATCH')
    for r in rows:
        m = metrics_of(r)
        require(r['complete_numeric_CCE'] == all(finite(m[k]) for k in ['Com', 'Cor', 'Eff']),
            'COMPLETE_NUMERIC_FLAG_MISMATCH')
        require(r.get('formal_eligible') is False, 'UNEXPECTED_FORMAL_ELIGIBILITY')
    require(sum(r['complete_numeric_CCE'] for r in rows) == summary['complete_numeric_CCE'], 'NUMERIC_COUNT_MISMATCH')
    for k in METRICS:
        require(sum(finite(r['metrics'][k]) for r in rows) == summary['component_coverage'][k], 'COVERAGE_MISMATCH:'+k)


def matching_binding(records, path, value):
    matches = [b for b in records if Path(b['path']).resolve() == Path(path).resolve()]
    require(len(matches) == 1 and matches[0]['sha256'] == value, 'SUMMARY_METADATA_BINDING_MISMATCH:'+str(path))


def development(meta, version):
    d = BASE / ('grounded_development_v'+str(version)); f = d / ('independent_fact_audit_v'+str(version))
    required = [d/'completion_summary.json', d/'analysis_verification.json', f/'summary.json', f/'inventory_verification.json']
    if not all(p.is_file() for p in required):
        return {'stage': 'dev_v'+str(version), 'state': 'pending_original_analysis_or_fact_audit', 'denominator': 5}
    s, verify, facts, inventory = [meta.load(p) for p in required]
    if s.get('actual_observations') != 5 or facts.get('status') != 'complete':
        return {'stage': 'dev_v'+str(version), 'state': 'pending_terminal_analysis_or_fact_audit', 'denominator': 5}
    rows = meta.load(d/'per_answer.json'); validate_observations(s, verify, rows, 5)
    matching_binding(verify['bindings'], d/'per_answer.json', meta.bindings[str((d/'per_answer.json').resolve())]['sha256'])
    matching_binding(verify['bindings'], d/'completion_summary.json', meta.bindings[str((d/'completion_summary.json').resolve())]['sha256'])
    require([r['anonymous_answer_id'] for r in rows] == ['A01','A02','A03','A04','A05'], 'FIXED_FIVE_IDS')
    require(facts['fixed_answers'] == 5 and [facts[k] for k in ['explicit_names_denominator', 'core_duration_denominator',
        'explicit_relation_denominator', 'ambiguity_group_denominator']] == [16,31,3,2], 'FIXED_FACT_DENOMINATORS')
    require([r['anonymous_answer_id'] for r in inventory] == ['A01','A02','A03','A04','A05']
        and all(r['source_bound'] is True for r in inventory)
        and sum(r['explicit_names'] for r in inventory) == 16 and sum(r['core_components'] for r in inventory) == 31,
        'FACT_INVENTORY_BINDING_REQUIRED')
    freeze_path = BASE / f'fact_audit_checker_v{version}/freeze.json'; freeze = meta.load(freeze_path)
    require(freeze['status'] == f'frozen_before_v{version}_generation', 'FROZEN_FACT_CHECKER_REQUIRED')
    matching_binding(facts['inputs'], freeze_path, meta.bindings[str(freeze_path.resolve())]['sha256'])
    plan = meta.load(d/'plan.json'); contract = meta.load(d/'expected_contract.json'); commands = meta.load(d/'actual_commands.json')
    require(plan['candidate_version'] == contract['round2_extraction']['version'] == f'source_bound_extraction_v{version}',
        'VERSION_CONTRACT_MISMATCH')
    require(plan['max_attempts'] == 1 and plan['num_ctx'] == 98304 and plan['max_output_tokens'] == 8192
        and plan['temperature'] == 0 and plan['timeout_seconds'] == 600, 'SETTINGS_SCOPE_CHANGED')
    require(len(contract['models']) == 1, 'SINGLE_DEVELOPMENT_JUDGE')
    settings = contract['models'][0]['settings']
    require(settings['num_ctx'] == 98304 and settings['max_output_tokens'] == 8192 and settings['temperature'] == 0
        and settings['timeout_seconds'] == 600 and settings['enable_thinking'] is False
        and settings['model'] == 'qwen3.8:27b-q8_0-local', 'ACTUAL_MODEL_SETTINGS_SCOPE')
    matching_binding(facts['inputs'], d/'expected_contract.json', meta.bindings[str((d/'expected_contract.json').resolve())]['sha256'])
    require(contract['round2_extraction']['module_sha256'] == freeze['grounded_module']['sha256'], 'CHECKER_CANDIDATE_MISMATCH')
    requests = sum(r.get('new_model_requests', 0) for r in commands if r['action'] == 'run')
    require(requests == 5, 'ACTUAL_COMPLETED_REQUEST_COUNT')
    return {'stage': f'dev_v{version}', 'kind': 'development', 'version': version, 'state': 'completed_metadata_verified',
        'denominator': 5, 'technical_successes': s['technical_successes'], 'technical_failures': s['technical_failures'],
        'complete_numeric_CCE': s['complete_numeric_CCE'], 'actual_new_requests': requests, 'expert_returns': s['expert_returns'],
        'formal_eligible': False, 'scientific_accuracy_established': False, 'source_summary': str(d/'completion_summary.json'),
        'source_facts': str(f/'summary.json'), 'coverage': s['component_coverage'], 'rows': rows, 'facts': facts,
        'commands': commands, 'contract': contract, 'plan': plan}


def followup(meta, kind, leaf):
    require(kind in {'E2','E4','confirmation'} and re.fullmatch(r'[A-Za-z0-9_]+', leaf), 'EXPLICIT_STAGE_DIRECTORY_REQUIRED')
    d = BASE / leaf; n = {'E2':21,'E4':30,'confirmation':16}[kind]
    if not (d/'completion_summary.json').is_file() or not (d/'analysis_verification.json').is_file():
        return {'stage': kind, 'state': 'pending_original_analysis', 'denominator': n}
    s = meta.load(d/'completion_summary.json'); v = meta.load(d/'analysis_verification.json')
    if s.get('actual_observations') != n or v.get('all_planned_terminal') is not True:
        return {'stage': kind, 'state': 'pending_all_terminal_analysis', 'denominator': n}
    rows = meta.load(d/'observations.json'); validate_observations(s, v, rows, n)
    matching_binding(v['bindings'], d/'observations.json', meta.bindings[str((d/'observations.json').resolve())]['sha256'])
    matching_binding(v['bindings'], d/'completion_summary.json', meta.bindings[str((d/'completion_summary.json').resolve())]['sha256'])
    plan = meta.load(d/'plan.json'); require(plan['phase'] == s['phase'] == kind, 'PHASE_BINDING_MISMATCH')
    details = {k:s[k] for k in ['planned_pairs','technical_complete_pairs','complete_numeric_pairs','all_pairs_same_contract',
        'within_groups','between_groups','same_repeat_metric_pairs','answer_denominator','category_summary',
        'common_n','common_answer_ids','common_means','common_aggregation','local_pre_request_failures'] if k in s}
    if kind == 'E2':
        require(s['planned_pairs'] == 15 and s['all_pairs_same_contract'] is True, 'E2_PAIR_CONTRACT')
    if kind == 'E4':
        require((s['within_groups'],s['between_groups'],s['same_repeat_metric_pairs']) == (160,80,240), 'E4_GROUP_DENOMINATORS')
    if kind == 'confirmation':
        require(len({r['anonymous_answer_id'] for r in rows}) == 8, 'EIGHT_CONFIRMATION_ANSWERS')
    commands=meta.load(d/'actual_commands.json')
    requests=sum(r.get('new_model_requests',0) for r in commands if r['action'].startswith('run'))
    if 'actual_new_requests' in s:
        require(requests==s['actual_new_requests'],'ACTUAL_REQUEST_COMMAND_COUNT')
    else:
        require(requests==s['planned_new_requests'],'COMPLETED_FOLLOWUP_REQUEST_COUNT')
    return {'stage':kind,'kind':kind,'state':'completed_metadata_verified','denominator':n,'source_summary':str(d/'completion_summary.json'),
        'version':plan.get('candidate_version','see_frozen_plan'),'technical_successes':s['technical_successes'],
        'technical_failures':s['technical_failures'],'complete_numeric_CCE':s['complete_numeric_CCE'],
        'actual_new_requests':requests,
        'expert_returns':s['expert_returns'],'formal_eligible':False,'scientific_accuracy_established':False,
        'coverage':s['component_coverage'],'rows':rows,'commands':commands,'details':details}


def supplement(meta):
    s=meta.load(OLD/'summary.json');v=meta.load(OLD/'verification.json');ind=meta.load(OLD/'independent_review.json')
    require(s['status']=='completed_offline_development_supplement' and (s['cases'],s['pairs'])==(21,15)
        and v['status']=='pass' and ind['status']=='software_and_provenance_verified', 'STEP_SUPPLEMENT_NOT_VERIFIED')
    require(v['output_hashes']['summary.json']==meta.bindings[str((OLD/'summary.json').resolve())]['sha256'],'STEP_SUPPLEMENT_HASH')
    chosen=[r for r in s['condition_results'] if r['mode']=='guarded_monotonic_one_to_one']
    require(len(chosen)==5 and all(r['pairs']==3 for r in chosen),'STEP_SUPPLEMENT_CONDITION_SCOPE')
    return {'historical_only':True,'included_in_new_request_counts':False,'included_in_original_SR_or_Com':False,
        'summary_path':str(OLD/'summary.json'),'condition_results':chosen,'claim_boundary':s['claim_boundary']}


def table(path, rows):
    if not rows: return
    keys=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)


def link(path, label):
    return f'[{label}](<{Path(path).resolve().as_posix()}>)'


def render(args):
    require({8,9}.issubset(set(args.versions)), 'BASELINE_V8_V9_REQUIRED_FOR_THIS_REPORT')
    meta=Metadata();stages=[development(meta,v) for v in args.versions]
    if 10 not in args.versions: stages.append({'stage':'dev_v10','state':'pending_report_inclusion_after_root_fact_completion','denominator':5})
    requested={}
    for spec in args.completed_stage:
        kind,leaf=spec.split('=',1);require(kind not in requested,'DUPLICATE_STAGE');requested[kind]=leaf
    stages += [followup(meta,k,requested[k]) if k in requested else {'stage':k,'state':'pending_not_read','denominator':n}
        for k,n in [('E2',21),('E4',30),('confirmation',16)]]
    sup=supplement(meta);completed=[s for s in stages if s['state']=='completed_metadata_verified']
    out=OUT/args.snapshot;require(re.fullmatch(r'[A-Za-z0-9_]+',args.snapshot),'SNAPSHOT_NAME');out.mkdir(parents=True,exist_ok=False)
    cover=[];values=[];facts=[];commands=[]
    for s in completed:
        for k in METRICS:
            category='direct_judge' if k in DIRECT else 'computed_EGES' if k in EGES else 'deterministic_steps' if k in ['sr','sp'] else 'derived'
            cover.append({'stage':s['stage'],'version':s['version'],'metric':k,'category':category,'finite':s['coverage'][k],
                'denominator':s['denominator'],'NA':s['denominator']-s['coverage'][k],'source':s['source_summary']})
        for row in s['rows']:
            for k,v in row['metrics'].items():
                values.append({'stage':s['stage'],'version':s['version'],'anonymous_answer_id':row['anonymous_answer_id'],
                    'question_id':row['question_id'],'trial_id':row['trial_id'],'judge':row.get('judge',s.get('contract',{}).get('models',[{}])[0].get('name')),
                    'repeat_index':row.get('repeat_index',0),'status':row['status'],'failure_stage':row.get('failure_stage'),
                    'metric':k,'value':v,'is_NA':v is None,'formal_eligible':False,'source':s['source_summary']})
        commands += [{'stage':s['stage'],'source':str(Path(s['source_summary']).parent/'actual_commands.json'),**r} for r in s['commands']]
        if 'facts' in s:
            f=s['facts'];metrics=[('names_exact',f['name_states'].get('exact',0),16),('raw_literal_names',f['raw_name_presence_separate']['states'].get('raw_literal_present',0),16),
                ('duration_literal',f['literal_numeric_components_retained'],31),('duration_record_bound',f['record_bound_numeric_components_retained'],31),
                ('duration_initial_scope',f['core_initial_scope_retained'],31),('fixed_positive_endpoint_edges',f['exact_endpoint_edges_retained'],3),
                ('fixed_positive_projections',f['exact_relation_projections_retained'],3),('ambiguity_explicit',f['ambiguity_states'].get('explicit_ambiguity_retained',0),2)]
            facts += [{'stage':s['stage'],'version':s['version'],'fact_measure':k,'retained':n,'fixed_denominator':d,'source':s['source_facts'],
                'not_semantic_accuracy_or_expert_gold':True} for k,n,d in metrics]
            commands.append({'stage':s['stage'],'action':'frozen_fact_audit','source':s['source_facts'],'argv':f['actual_command'],'new_model_requests':0})
    table(out/'component_coverage.csv',cover);table(out/'per_answer_metrics.csv',values);table(out/'fixed_fact_coverage.csv',facts)
    table(out/'historical_step_supplement.csv',sup['condition_results']);save(out/'actual_commands_index.json',commands)
    public=[]
    for s in stages:
        public.append({k:v for k,v in s.items() if k not in ['rows','commands','contract','plan','facts']})
    zh=['本报告仅汇编已终态并完成原分析核验的结果。技术成功、数值完整和来源事实核查分别统计；不作科学资格通过判定。',
        '', '|阶段/版本|技术成功|技术失败|完整 CCE|状态|','|---|---:|---:|---:|---|']
    zhfindings=[]
    en=['## Methods','',
        'Candidate extraction versions were evaluated on the same five previously exposed development answers, with one request per answer and no retries. Each version had its own frozen source-specific schema, prompt, input references, model contract and checker. The recorded local model alias was `qwen3.8:27b-q8_0-local`; its service metadata reported family `qwen35`, parameter size 27.3B and Q8_0 quantization. The alias does not establish a distinct vendor model identity. Generation used temperature 0, a 98,304-token context allocation, an 8,192-token output limit, a 600-s timeout, and thinking disabled.',
        '', 'The original scoring formulas, demands, knowledge base and deterministic BioProBench SR/SP inputs were retained. Original analyzers replayed successful raw conversions and numerical outputs; this report only checks completed metadata and finite-value counts. Missing values remain NA. Technical completion, finite Com/Cor/Eff, fixed-inventory retention and scientific validity are separate outcomes. The fixed development inventory comprises 16 explicit names, 31 duration components, three positive relations and two ambiguity groups; these units are nested within five answers and are not independent samples.',
        '', '## Results','']
    for s in stages:
        if s['state']!='completed_metadata_verified':
            zh.append(f"|{s['stage']}|待定|待定|待定|{s['state']}|");continue
        n=s['denominator'];zh.append(f"|{s['stage']}|{s['technical_successes']}/{n}|{s['technical_failures']}/{n}|{s['complete_numeric_CCE']}/{n}|原分析完成|")
        if 'facts' in s:
            f=s['facts'];sentence=(f"{s['stage']}：名称精确保留 {f['name_states'].get('exact',0)}/16；时长字面/操作记录绑定/initial 范围分别为 "
                f"{f['literal_numeric_components_retained']}/31、{f['record_bound_numeric_components_retained']}/31、{f['core_initial_scope_retained']}/31；"
                f"固定正关系端点 {f['exact_endpoint_edges_retained']}/3，可投影 {f['exact_relation_projections_retained']}/3；"
                f"显式歧义保留 {f['ambiguity_states'].get('explicit_ambiguity_retained',0)}/2。"
                f"s_label 与 s_time 有限覆盖分别为 {s['coverage']['s_label']}/5、{s['coverage']['s_time']}/5；"
                f"事实分项保留不代表全流程时长或标签得分可用。")
            zhfindings += ['',sentence+' '+link(s['source_facts'],'事实审计')+'；'+link(s['source_summary'],'原分析')+'。']
            en.append(f"Version {s['version']} completed {s['technical_successes']}/5 requests technically, with {s['complete_numeric_CCE']}/5 complete CCE observations. Exact converted names were retained for {f['name_states'].get('exact',0)}/16 inventory entries; record-bound duration components for {f['record_bound_numeric_components_retained']}/31; and fixed positive relation projections for {f['exact_relation_projections_retained']}/3. Label and time scores were finite for {s['coverage']['s_label']}/5 and {s['coverage']['s_time']}/5 answers, respectively. " + link(s['source_summary'],'Analysis')+'; '+link(s['source_facts'],'fixed-inventory audit')+'.\n')
            en.append('Version-specific intervention recorded by the frozen checker: '+f['bundle']+'\n')
        else:
            en.append(f"{s['stage']} yielded {s['technical_successes']}/{n} technical successes and {s['complete_numeric_CCE']}/{n} complete CCE observations. Original phase-specific denominators and summaries are retained in report_summary.json. "+link(s['source_summary'],'Original analysis')+'.\n')
    zh += zhfindings
    zh += ['', 'v8 与 v9 在同一五份开发答案上得到不同结果：固定正关系可投影从 2/3 到 3/3，但技术通过、名称及时长保留减少，两版均无完整 CCE。这些单次开发观察不能证明整体改善或跨模型稳定性。原始名称字面出现不等于通过来源边界或转换；关系端点存在也不证明关系语义正确。失败答案仍留在分母，独立已知 SR/SP 不因 judge 失败而删除。',
        '', '已完成的旧 step_representation_v3 为独立条件性词法覆盖补充：guarded one-to-one/monotonic 模式在三对删步骤中参考覆盖下降，三对相邻合并和三对编号等价变体覆盖不变；monotonic 模式在三对改序中覆盖下降。参数删除三对仍不响应。此结果只涉及词法动作/对象及文本顺序，不是原 SR 的改进结果，也不是生物学顺序正确性或专家验证；未进入原 Com。'+link(OLD/'summary.json','旧补充真实结果')+'。',
        '', '限制：版本复用了已暴露开发答案，不能充当前瞻确认。软件核验通过不等于科学准确；专家回传仍为 0。本次报告不读取 raw、trial、原文、封存确认或专家留出，不重复 converter、embedding 或评分。尚未纳入的阶段只标 pending，不能将现有表格完整性视为实验成功。']
    en += ['The mixed changes between versions 8 and 9 do not establish overall improvement. These are repeated development observations on the same five exposed answers, not prospective confirmation or an evaluator-stability experiment. Raw literal presence, endpoint presence, accepted projection and scientific correctness are distinct. No expert validation is claimed.',
        '', 'A previously completed, separate lexical coverage supplement (`step_representation_v3`) used 21 texts and 15 controlled pairs. Under guarded one-to-one/monotonic matching, reference coverage decreased in 3/3 step-deletion pairs and was unchanged in 3/3 adjacent-merge and 3/3 numbering-equivalence pairs. Monotonic matching decreased coverage in 3/3 order-change pairs; parameter deletion remained unresponsive in 3/3. This is conditional textual coverage, not improved original SR, biological order accuracy or a replacement component of Com. '+link(OLD/'summary.json','Historical supplement')+'.',
        '', 'Phases not explicitly included with completed original analyses remain pending. Metric-level grids, candidate facts and multiple versions are not independent answer samples; no additional statistical test or score was introduced.']
    (out/'RESULTS_zh.md').write_text('\n'.join(zh)+'\n',encoding='utf8');(out/'METHODS_RESULTS_en.md').write_text('\n'.join(en)+'\n',encoding='utf8')
    save(out/'report_summary.json',{'status':'metadata_snapshot_not_scientific_acceptance','created_utc':datetime.now(timezone.utc).isoformat(),
        'stages':public,'historical_step_supplement':sup,'reported_completed_stage_count':len(completed),'expert_returns':0,
        'new_model_calls':0,'new_embeddings':0,'new_score_computations':0,'protected_scientific_input_reads':0})
    (out/'producer_snapshot.py').write_bytes(Path(__file__).read_bytes())
    save(out/'source_manifest.json',{'inputs':list(meta.bindings.values()),'producer':bind(__file__),
        'producer_exact_bytes':bind(out/'producer_snapshot.py'),
        'nonrecursive_binding_policy':'Only listed public metadata is read; embedded raw/source bindings are not followed.'})
    save(out/'actual_command.json',{'argv':[sys.executable,*sys.argv],'new_model_calls':0,'new_score_computations':0})
    outputs=[bind(p) for p in out.iterdir() if p.is_file()]
    save(out/'verification.json',{'status':'pass_metadata_consistency_only','stage_count':len(completed),
        'component_rows':len(cover),'per_answer_metric_rows':len(values),'fixed_fact_rows':len(facts),'outputs':outputs,
        'original_scoring_not_rerun':True,'claims_require_original_evidence':True,'new_model_calls':0})
    return {'status':'rendered_completed_metadata_snapshot','output':str(out),'completed_stages':[s['stage'] for s in completed],
        'component_rows':len(cover),'per_answer_metric_rows':len(values),'new_model_calls':0}


def self_check():
    checks=[]
    def reject(name,fn):
        try:fn()
        except (ValueError,KeyError): checks.append(name);return
        raise AssertionError(name)
    m={k:None for k in METRICS};m['sr']=m['sp']=0
    row={'trial_id':'t','status':'failed','metrics':m,'complete_numeric_CCE':False,'formal_eligible':False}
    s={'status':'experiment_complete_not_scientific_validation','planned_observations':1,'actual_observations':1,'pending':0,
        'technical_successes':0,'technical_failures':1,'complete_numeric_CCE':0,'component_coverage':{k:int(finite(v)) for k,v in m.items()}}
    v={'status':'pass','terminal_observations':1,'all_planned_terminal':True}
    validate_observations(s,v,[row],1);checks.append('known_zero_and_failure_NA_preserved')
    reject('partial_not_complete',lambda:validate_observations({**s,'pending':1},v,[row],1))
    reject('failure_not_success',lambda:validate_observations({**s,'technical_successes':1},v,[row],1))
    reject('missing_not_zero',lambda:validate_observations({**s,'component_coverage':{**s['component_coverage'],'Com':1}},v,[row],1))
    reject('formal_not_inferred',lambda:validate_observations(s,v,[{**row,'formal_eligible':True}],1))
    reject('no_source_reads',lambda:Metadata().load(BASE/'source_documents/A01.json'))
    reject('no_sealed_reads',lambda:Metadata().load(BASE/'sealed/summary.json'))
    reject('no_trial_reads',lambda:Metadata().load(BASE/'run/completion_summary.json'))
    return {'status':'pass','checks':checks,'count':len(checks),'new_model_calls':0}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['draft-check','render'])
    p.add_argument('--versions',type=int,nargs='+',choices=[8,9,10],default=[8,9])
    p.add_argument('--completed-stage',action='append',default=[])
    p.add_argument('--snapshot',default='snapshot_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    a=p.parse_args();require(len(set(a.versions))==len(a.versions),'DUPLICATE_VERSION')
    result=self_check() if a.action=='draft-check' else render(a);print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
