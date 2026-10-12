"""Materialize explicitly authored review notes; this is not an automatic judge."""
import json
import sys
from pathlib import Path

sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
from cce_source_context_claim_audit_v1 import bind, save, ROOT

P=ROOT/'artifacts/cce_validation/optimizer_round3_20261011/source_context_validation_proposal_01'
R=ROOT/'artifacts/cce_validation/reference_recovery'
OLD=ROOT/'artifacts/cce_validation/optimizer_round3_20261011/problem_cycles/development_rubric_evidence_cycle01'
C='consistent_with_bound_source'
X='conflicts_with_bound_source'
U='not_supported_by_current_sources'
O='not_claimed_or_explicitly_unresolved'
notes={'reviewer_role':'author_not_independent_expert',
    'source_anchors':{'table':bind(R/'recovered_supplements/aau8355_SM_p12.txt'),
        'main':bind(R/'fdisco_primary_passage.txt'),
        'rubric':bind(ROOT/'prompts/eval_oeq_teacher_rubric.txt'),
        'cases':bind(P/'cases.json'),
        'references':bind(OLD/'execution_01/references_unchanged.json'),
        'arithmetic':bind(P/'conditional_arithmetic_check_01.json')},
    'planned_priority_reviews':[],'exploratory_reviews':[],
    'completeness_denominator_review':[],
    'score_corrections_applied':False,'expert_forms_modified':False,
    'annotation_scope':'Eight predeclared priority metric records times three conditions, plus separately labeled exploratory claims. Selected claims only; not every statement or an accuracy estimate.'}


def claim(category,focus,basis,*anchors):
    return {'category':category,'focus_zh':focus,'basis_zh':basis,'source_anchors':list(anchors)}


def add(a,k,m,*claims,exploratory=False):
    notes['exploratory_reviews' if exploratory else 'planned_priority_reviews'].append({
        'observation_id':a+'_'+k,'metric':m,'claims':list(claims)})


add('A01','K0','co_param',
    claim(C,'作者表给出全脑 THF 的名义时长。','该名义比较值与附表对应操作一致。','table'),
    claim(O,'未提及作者允许减半这一限定。','原理由不包含这一选项；旧实际请求也缺少定量减半限定，前期输入审计已经记录该遗漏。','table','references'),
    claim(U,'将相对于名义值的缩短作为不足和扣分的依据。','附表同时存在减半选项；仅与名义值比较没有覆盖该选项。其他路线差异仍保留，不能据此直接重判整项。','table','rubric'))
for k in ['K1','K2']:
    add('A01',k,'co_param',
        claim(C,'承认作者允许为保留荧光而缩短至一半。','这与附表注释一致。','table'),
        claim(U,'要求答案明确声明采用减半选项，否则仍以偏离标准扣分。','当前量表和作者附表没有这项额外的声明要求；该要求不足以单独支持所给档位。','rubric','table'))
for k in ['K0','K1','K2']:
    add('A01',k,'co_order',claim(U,
        '以染色先后或水相到 THF 之间缺少额外过渡作为顺序扣分依据。',
        '绑定的 FDISCO 核心参考没有建立该标记条件下的必要先后关系或该额外过渡；K1 还承认直接过渡可被该方法接受。需条件相容的证据，不能由通用有机溶剂流程直接推定。',
        'main','references','rubric'))
for k in ['K0','K1']:
    add('A02',k,'co_param',claim(U,'依据厚度和定性扩散推断时间不足，并赋中间档。',
        '3 mm 参考明确未定时且不插值；理由没有给出支持 50% 档的适用比较值。一般扩散关系本身不能给出当前时间差比例。','references','rubric'))
add('A02','K2','co_param',
    claim(C,'承认来源未报告 3 mm 专用时长，并将担忧称为定性。','与当前注册参考的未定时说明一致。','references'),
    claim(U,'仍将定性不足判断作为 1 分依据。','新增的全脑或大块通常需多日的描述没有绑定适用比较值，也未证明原中间档的百分比条件。','references','table','rubric'))
add('A03','K0','co_param',
    claim(C,'承认来源没有标准化的 3 mm 专用时长。','当前 3 mm 参考明确缺少精确时间。','references'),
    claim(U,'以通常需要过夜或多日推断不足并给中间档。','没有匹配的定量比较基准或 50% 档依据。','references','rubric'))
add('A03','K1','co_param',claim(U,'按定性厚度推断 THF 和 DBE 时间不足。',
    '没有新增与该 3 mm 条件相容的时间证据；判为偏差档仍缺百分比基准。','references','rubric'))
add('A03','K2','co_param',
    claim(U,'将 12–24h+ 描述为该厚度的典型比较时间。','绑定资料不含此 3 mm 专用定量基准。','references'),
    claim(X,'同一理由写超过 50%，又归入 50% 以内档。','原 1 分档写为偏差在 50% 以内；独立条件算术也表明模型自己举出的比较值不满足该条件，但算术不验证比较值本身。','rubric','arithmetic'))
add('A04','K0','co_param',
    claim(C,'承认来源没有报告 3 mm 专用时长。','与参考元数据一致。','references'),
    claim(U,'判断 12h 对 3 mm 不足并赋 1 分。','没有适用基准来支撑这一不足判断及其量表档位。','references','table','rubric'))
add('A04','K2','co_param',claim(U,'认为 12h 对 3 mm 保守、适当，并赋满分。',
    '理由方向改变，但没有补充该样本条件的直接定量证据。保留原 2 分，不把提高自动解释为科学准确性改善。','references','rubric'))

add('A05','K0','c_param',claim(U,'在承认时间、温度、浓度均有时，以摇动和 pH 调整体积缺失给 2 分。',
    '没有说明必要细节分母及原 2 分所述缺温度或浓度条件如何成立。记录落档依据缺口，不自动给满分。','rubric','cases'))
for k in ['K1','K2']:
    add('A05',k,'c_param',claim(X,'将缺少染色参数作为扣分理由。',
        '题目仅要求首行选择策略，随后仅列透明处理、RI 匹配和保存/成像前处理。原范围规则要求只评价题目要求的工作；不能因没有展开染色操作参数而扣此项。','cases','rubric'))
add('A05','K0','co_order',
    claim(C,'承认脱水到 RI 匹配的核心顺序符合 FDISCO。','主文描述该方法的两项核心处理。','main'),
    claim(U,'仍以通用脱脂或额外平衡步骤缺失扣顺序分。','未指出本方法本条件必须存在该过渡的来源；通用其他路线清单不能独立建立必要性。','main','references','rubric'))
for k in ['K1','K2']:
    add('A05',k,'co_order',
        claim(X,'因未在操作序列中展开染色阶段而扣顺序分。','题目明确限定需列出的操作范围；该扣分要求超出题目。','cases','rubric'),
        claim(U,'将染色或复水转换描述为本 FDISCO 序列的必要操作。','核心参考没有为当前输出范围确立所声称的必要转换；需要区别整项生物学目标与本题指定输出。','main','references','cases'))
add('A05','K0','co_param',
    claim(X,'把脱水与 DBE 时间一起置于 12h 每步的比较中。','附表对应操作的名义时长不同；DBE 行不是该 THF 比较值。','table'),
    claim(U,'由时间偏离和定性扩散推出物理违规并给 0。','参数偏离附表与满足原物理不可能档需要分别论证，现有理由不足以建立后者。','table','rubric'))
add('A05','K1','co_param',
    claim(X,'称 THF 和 DBE 时间均短于 12h+ 的标准。','DBE 在绑定全脑附表中有自己的比较值，不能共用 THF 的时长。','table'),
    claim(U,'认为不至于物理不可能，于是给 1 分。','排除极端例子没有证明原中间档的百分比条件。','rubric'))
add('A05','K2','co_param',
    claim(C,'将 THF 与 DBE 分别对应各自附表值，并识别 DBE 方向为增加。','对应关系与附表一致，原操作比较值错配在此返回中修正。','table'),
    claim(C,'同时考虑作者减半选项。','该选项存在于附表注释。','table'),
    claim(X,'明确承认偏差超过 50%，仍决定给 1 分。','这未满足原中间档的百分比条件；模型也明确指出不能仅凭大偏差证明物理不可能。原值保留，不替换为 0。','rubric','table'))

add('A03','K1','co_order',claim(U,'以额外过渡缺失及核染位置欠优扣顺序分。',
    '该新增顺序分变化不属于原八个优先项。理由承认核心顺序正确，也未给出本条件下必需额外过渡的来源。','main','references','rubric'),exploratory=True)
add('A01','K2','co_method',claim(U,'将 BABB-Df 直接称为有效 FDISCO 变体，并赋 2 分。',
    '当前绑定的核心方法参考使用 DBE；物理兼容、方法身份和经验证的变体需要分别核查。现有材料不足以认证该升分，亦不据此宣称替代路线不可行。','references','rubric'),exploratory=True)
add('A04','K2','co_method',claim(U,'在举例中将 BABB 列为不兼容试剂。',
    '给定参考未建立这一一般化不兼容判断；它与 A01/K2 的变体断言方向不同，需条件相容的独立依据。没有据此更改本答案分值。','references','rubric'),exploratory=True)

add('A04','K1','co_param',claim(U,'称该 3 mm 条件通常需要 24–48h 或更长，并据此给 1 分。',
    '当前资料没有该 3 mm 专用比较值；理由用定性担忧和排除极端例子代替适用经验基准及明确的百分比条件。该实际返回已单独阅读。','references','rubric'))

for a in ['A01','A02','A03','A04','A05']:
    for k in ['K0','K1','K2']:
        notes['completeness_denominator_review'].append({'observation_id':a+'_'+k,
            'explicit_numerator_and_denominator':False,
            'author_note_zh':'理由举出参数类型或宣称各步骤详细，但没有明确枚举必要细节分母及已提供数量。这是可复核性记录，不追溯计作旧评分错误。'})

if __name__=='__main__':
    assert len(notes['planned_priority_reviews'])==24, 'Complete all actual author reviews before writing.'
    assert len(json.loads((P/'readout_complete_01/observations.json').read_text(encoding='utf-8')))==15
    save(P/'source_claim_annotations_01.json',notes)
    print(json.dumps({'planned_priority_reviews':24,'exploratory_reviews':3,'new_model_calls':0,'expert_judgments':0}))
