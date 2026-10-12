"""Freeze source-reviewed q146-only applicability before any heldout step scores."""
from pathlib import Path
from datetime import datetime, timezone
import copy
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import cce_validation as core

BASE = ROOT / 'artifacts/cce_validation'
SRC = BASE / 'reference_recovery/clearsee_boneclear_source_recovery_v1'
OUT = BASE / 'reference_recovery/clearsee_holdout_step_activation_v1'
sha = core.filehash


def main():
    assert not (BASE / 'holdout_source_steps_v1/run.json').exists(), 'Freeze must precede scoring.'
    candidate = core.read(SRC / 'candidate.json')
    assert sha(SRC / 'candidate.json') == 'ad6647cb12dd00a46dbd721cd5a53665a6f627112cb07a1f4ebcce3a3b031f83'
    review = SRC / 'review/source_scope_review.json'
    assert sha(review) == 'dd6802b9e2c53d418a0cee6d94dc11af3c88277a10636528e48b74d0b81db328'
    cases_path = BASE / 'judges/local_extraction_holdout_v1/sealed/cases.json'
    case = next(c for c in core.read(cases_path)['cases'] if c['anonymous_answer_id'] == 'A06')
    assert case['question_id'] == 146
    ref = copy.deepcopy(candidate['references'][0])
    route, declaration = core.selected_route(case['model_response'], [ref])
    assert route == 'ClearSee' and declaration.strip().lower() == 'clearsee', declaration
    assert len(ref['steps']) == 4 and ref['question_ids'] == [145, 146]
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ('source_manifest.json', 'source_passages.json', 'clearsee_evidence_gate.json'):
        (OUT / name).write_bytes((SRC / name).read_bytes())
    ref['reference_id'] = 'CLEARSEE_2015_POSTFIXED_SEEDLING_WALL_Q146_CONDITIONAL_V1'
    ref['question_ids'] = [146]
    ref['applicability']['question_ids'] = [146]
    ref['activation_status'] = 'conditional_author_branch_step_diagnostic_only'
    ref['evidence_manifest_path'] = str(OUT / 'source_manifest.json')
    ref['source_passages_path'] = str(OUT / 'source_passages.json')
    ref['source_candidate_parent'] = {'path':str(SRC / 'candidate.json'), 'sha256':sha(SRC / 'candidate.json')}
    ref['root_scope_decision'] = 'Only A06/q146: no prescribed wall dye. q145/SCRI2200 remains ineligible for this source branch. Full scientific suitability, exact size and whole-seedling dual-channel outcome remain unconfirmed.'
    assert ref['steps'] == candidate['references'][0]['steps']
    core.write(OUT / 'references.json', {'schema_version':'clearsee-q146-conditional-step-activation-v1', 'references':[ref]})
    dependencies = [Path(__file__), SRC / 'candidate.json', review, SRC / 'clearsee_build_verification.json',
                    OUT / 'source_manifest.json', OUT / 'source_passages.json', OUT / 'clearsee_evidence_gate.json',
                    Path(ref['source_path']), cases_path, ROOT / 'scripts/cce_validation.py']
    decision = {'status':'frozen_before_step_scores','created_utc':datetime.now(timezone.utc).isoformat(),
        'allowed_anonymous_answer_ids':['A06'],'allowed_question_ids':[146], 'excluded_question_ids':[145],
        'exclusion_reason':'q145 requires SCRI Renaissance2200; the author branch uses Calcofluor White without established substitution. This is insufficient source support, not a finding that SCRI is incompatible.',
        'scope':'Four source operations from a fixed-specimen start; continuing storage separate. Conditional author-branch SR/SP only. Not complete task validation, CCE, or independent holdout accuracy.',
        'known_version_declaration_checked_before_scoring':declaration,
        'version_check_scope':'This exact fixed A06 declaration; unchanged core is not a general version-disambiguation solution.',
        'all_15_original_cases_will_be_processed':True,'all_four_source_operations_preserved':True,
        'scientific_target_satisfaction':'pending','expert_returns':0,'formal_eligible':False,
        'judge_results_or_scientific_scores_read':False,'new_model_requests':0,
        'references_sha256':sha(OUT / 'references.json'),
        'input_sha256':{str(p):sha(p) for p in dependencies},
        'actual_command':[sys.executable,*sys.argv],'cwd':str(Path.cwd())}
    core.write(OUT / 'scope_decision.json',decision)
    (OUT / 'README.md').write_text('# ClearSee q146 条件性步骤扩展\n\n固定后作者四操作完整保留，仅 A06/q146 进入独立 SR/SP 诊断。A17/q145 明确要求 SCRI2200，作者 Calcofluor 来源不足以满足该任务，继续 NA；没有为凑分删掉壁染操作。\n\n来源经独立原文核对；精确长度、整幼苗双通道、科学目标与专家确认仍待定。没有读取原 judge 科学输出或合成 CCE。原15份选择、原模型结果及人工表不变。\n\n[范围决策](scope_decision.json)、[冻结参考](references.json)、[原文证据](source_manifest.json)、[原始作者候选与独立核查](../clearsee_boneclear_source_recovery_v1/README.md)。\n',encoding='utf-8')
    print(json.dumps({'status':decision['status'],'qids':[146],'source_operations':4,'references_sha256':decision['references_sha256'],'new_model_requests':0}))


if __name__ == '__main__':
    main()
