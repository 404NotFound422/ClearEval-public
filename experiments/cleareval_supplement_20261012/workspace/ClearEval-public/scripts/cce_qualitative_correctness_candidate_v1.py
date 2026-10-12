"""Prepare a prospective qualitative-Cor candidate; never send model requests.

Keeps the four Cor ranges and aggregation, changes the co_param decision rule.
The new rule is not retroactively applied to old scores. Source schema and full
answer/reference material are inherited from grounded extraction v11.
"""
import argparse
import difflib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_grounded_extraction_v11 as ground
import cce_scoped_midpoint_scorer_v1 as io

VERSION = 'qualitative-correctness-scope-v1'

UNCERTAINTY = '''[JUDGMENT SCOPE AND MISSING EVIDENCE]
Judge the protocol as submitted, under the QUESTION's stated initial conditions.
The LLM evaluates required structure, ordering, method-reagent coherence, and
explicit common-sense physical or chemical errors. EGES calculates numerical
method suitability, fluorescence compatibility, RI matching and time suitability.
Do not repeat EGES numerical optimization, invent an applicable reference value,
or demand wet-lab proof before applying this qualitative rubric.
For every direct score, give a concise source-grounded reason: relevant answer
Unit, criterion, observed issue or absence of a criterion-defined issue, score.
The lack of a numerical duration reference alone does not make qualitative
co_param unknown. Use the criteria below. Do not award full marks automatically
just because a parser succeeded or a method name is recognized.
If a true source contradiction or uninterpretable identity prevents the relevant
criterion from being judged, keep only that sub-score null and state the exact
obstacle. A rubric-defined omission or failure receives its defined score.
Preserve other assessable components. Missing totals must not be imputed.
'''

PARAMETER = '''2.3 参数的常识性物理合理性 (Co_param, 0–2分)

本项仅作定性审查；数值时间适配、折射率匹配、方法及荧光兼容性由 EGES 计算。
不以相对文献时长或浓度的百分比偏差落档，不臆造组织厚度对应的标准时间。

2分：在题干范围和答案已述条件下，未发现明确的物理常识违背或相互冲突的参数要求。
这一分数表示未识别出本判项的定性错误，不代表参数经过湿实验验证或达到最佳有效性。

1分：原文存在可具体定位、非致命的参数要求矛盾或常识性不合理处；说明涉及的两个条件、
为什么冲突以及为什么未达到0分。不能仅因“缺少标准参考数值”或“可能不够理想”给1分。

0分：原文明示的条件违反基本物理常识，导致所述操作明显不可执行或直接破坏所需样本。
判断必须指出实际条件及其物理后果，不能只依据与某篇 protocol 数值不同。

必要参数未写出由 C_param 评价；在 EGES 中保留无法计算的相应分项，
不要把“没有写出”改写成一个假想的错误数值，也不要重复扣成 Co_param=0。

'''

LABEL_NOTE = '''[LABEL ROLE CLARIFICATION]
Extract fluorophore -> target/probe relationships at the original marker_dict
level. MAP2 is the target; anti-MAP2 is the antibody; Alexa Fluor 488 is the dye.
An explicit MAP2 + Alexa Fluor 488 statement supports that relationship without
requiring a clone or an entire antibody chain. Preserve explicit uncertainty
when the relationship is actually absent or contradictory.
Native GFP/EGFP/tdTomato and direct stains such as DAPI/DiI do not require an
external antibody marker. Record their source-declared standalone signal role;
do not create a missing antibody relationship for them. This does not by itself
establish coverage of every biological structure requested by the task.
Distinguish alternatives in a heading from the reagent selected in the actual
operation. When two assignments remain possible, retain that ambiguity. A
generic Alexa Fluor mention can refer to the same channel as a named dye later
in the source; do not invent another independent label. Keep exact dye names;
AF-family approximation is performed by the versioned numerical scorer, not by
rewriting the submitted answer or claiming identical retention for all AF dyes.
'''


def replace_block(text, begin, end, replacement):
    if text.count(begin) != 1 or text.count(end) != 1:
        raise ValueError('Expected one rubric section boundary: ' + begin)
    first, rest = text.split(begin)
    _, last = rest.split(end)
    return first + replacement + '\n' + end + last


def make_prompt(case, doc):
    original = ground.make_prompt(case, doc)
    updated = replace_block(original, '[UNCERTAINTY CONTRACT]', '[QUESTION]', UNCERTAINTY)
    updated = replace_block(updated, '2.3 参数范围物理合理性 (co_param, 0–2分)',
                            '2.4 化学安全性 (co_chem, 0–1分)', PARAMETER)
    return updated + '\n' + LABEL_NOTE


def schema_for_document(doc):
    return ground.schema_for_document(doc)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    cases = io.read(args.cases)
    if isinstance(cases, dict):
        cases = cases['cases']
    args.out.mkdir(parents=True, exist_ok=True)
    matrix = []
    for case in cases:
        doc = ground.document(case['model_response'], ground.source_id_for_case(case))
        original, revised = ground.make_prompt(case, doc), make_prompt(case, doc)
        identifier = case.get('anonymous_answer_id', case['case_id'])
        folder = args.out / identifier
        folder.mkdir(exist_ok=True)
        (folder / 'prompt.txt').write_text(revised, encoding='utf-8')
        (folder / 'prompt.diff').write_text(''.join(difflib.unified_diff(
            original.splitlines(True), revised.splitlines(True),
            fromfile='archived_rubric_scope', tofile=VERSION)), encoding='utf-8')
        io.save(folder / 'schema.json', schema_for_document(doc))
        io.save(folder / 'source_document.json', doc)
        # Source material is compared separately from the changed rubric.
        assert doc['text'] == case['model_response']
        assert '时间/浓度偏差在 50%' not in revised
        assert '[UNCERTAINTY CONTRACT]' not in revised
        matrix.append({'case_id': case['case_id'], 'anonymous_answer_id': identifier,
            'question_id': case['question_id'], 'source_document': io.bind(folder/'source_document.json'),
            'prompt': io.bind(folder/'prompt.txt'), 'schema': io.bind(folder/'schema.json'),
            'status': 'prepared_not_requested', 'required_judge_family': 'Qwen3.8_or_explicitly_authorized_Codex',
            'prospective_confirmation': False, 'development_exposed': True})
    io.save(args.out / 'manifest.json', {'version': VERSION, 'cases': io.bind(args.cases),
        'candidate': io.bind(__file__), 'grounded_builder': io.bind(ground.__file__),
        'original_prompt': io.bind(ROOT/'prompts/eval_oeq_teacher_rubric.txt'),
        'new_model_requests': 0, 'historical_scores_replaced': False,
        'Cor_scales': [3, 2, 2, 1], 'co_param_definition_changed': True,
        'SR_SP_EGES_redefined': False, 'observations': matrix})
    print(json.dumps({'prepared': len(matrix), 'new_model_requests': 0}))


if __name__ == '__main__':
    main()
