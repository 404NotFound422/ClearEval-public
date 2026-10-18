"""Isolated, closed-world transcription candidate. No scoring or tier inference.

Supports only the nine reviewed question stems. A changed stem must be reviewed,
not matched by keyword or silently reduced to a legacy scalar tissue tier.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
VERSION = 'sample-scope-candidate-v1'
SUPPORTED = {165, 166, 167, 168, 221, 222, 223, 224, 240}

class ContractError(ValueError):
    pass

def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def anchor(text, quote):
    if text.count(quote) != 1:
        raise ContractError('Anchor must occur exactly once')
    start = text.index(quote)
    return {'start': start, 'end': start + len(quote), 'quote': quote}

def dimension(axis, value, unit):
    return {'axis': axis, 'value': value, 'unit': unit,
            'normalized_value_mm': value * {'cm': 10, 'mm': 1, 'μm': .001}[unit],
            'approximate': True}

def sample(text, sid, identity, form, quotes, dims):
    return {'sample_id': sid, 'identity': identity, 'form': form,
            'dimensions': dims, 'anchors': [anchor(text, q) for q in quotes],
            'tier': 'UNKNOWN', 'reference_applicability': 'UNKNOWN',
            'time_reference': 'UNKNOWN', 'ri_reference': 'UNKNOWN',
            'physical_specimen_count': 'UNKNOWN', 'group_membership': 'UNKNOWN'}

def _literal_contract(question):
    qid, text = question['question_id'], question['question']
    if qid not in SUPPORTED:
        raise ContractError('Unreviewed question id')
    if qid in {165, 166, 167, 168}:
        samples = [
            sample(text, 'spinal_segment', '连续脊髓段', 'CONTINUOUS_SEGMENT',
                   ['一类为长约 3 cm 的连续脊髓段'], [dimension('length', 3, 'cm')]),
            sample(text, 'brain_block', '保留丘脑至体感皮层连接的连续脑块', 'CONTINUOUS_BLOCK',
                   ['另一类为保留丘脑至体感皮层连接的连续脑块，约 10 mm × 8 mm × 6 mm'],
                   [dimension(f'unspecified_axis_{i}', v, 'mm') for i, v in enumerate([10, 8, 6], 1)])]
        context = [anchor(text, '两类样本分别成像')]
    elif qid in {221, 222, 223, 224}:
        samples = [
            sample(text, 'retina', '完整视网膜', 'WHOLE_RETINA', ['完整视网膜（直径约 5 mm）'],
                   [dimension('diameter', 5, 'mm')]),
            sample(text, 'lgn', 'LGN', 'SEPARATED_TISSUE_BLOCK', ['LGN（约 2 mm × 1.5 mm × 1 mm）'],
                   [dimension(f'unspecified_axis_{i}', v, 'mm') for i, v in enumerate([2, 1.5, 1], 1)]),
            sample(text, 'v1', 'V1', 'SEPARATED_TISSUE_BLOCK', ['V1（约 3 mm × 3 mm × 2 mm）'],
                   [dimension(f'unspecified_axis_{i}', v, 'mm') for i, v in enumerate([3, 3, 2], 1)])]
        context = [anchor(text, '再分离用于成像'), anchor(text, '两组样本分别分析'),
                   anchor(text, '各分离组织块仅分析内部可见的局部走行与终末，不恢复已切断的块间连续路径')]
    else:
        samples = [sample(text, 'organoid', '人源肠道类器官', 'WHOLE_ORGANOID',
                          ['一个直径约 300 μm 的人源肠道类器官', '尽量避免破坏类器官整体结构'],
                          [dimension('diameter', 300, 'μm')])]
        context = [anchor(text, '1–2 天时限从固定完成后开始，包含所选标记、透明化和成像前处理')]
    return {'schema_version': VERSION, 'question_id': qid, 'question_sha256': digest(text),
            'sample_id_semantics': 'QUESTION_LOCAL_OBJECT_CLASS_NOT_PHYSICAL_SPECIMEN',
            'samples': samples, 'context_anchors': context,
            'cross_sample_aggregation': 'UNKNOWN', 'question_level_tier': 'UNKNOWN',
            'question_level_time': 'UNKNOWN', 'question_level_ri': 'UNKNOWN',
            'deployment_status': 'ISOLATED_CANDIDATE'}

def build_contract(question):
    # Complete stem binding prevents stale reviewed facts being reused on changed tasks.
    approved = json.loads((HERE / 'fixtures' / 'questions.json').read_text())
    matches = [q for q in approved if q['question_id'] == question.get('question_id')]
    if len(matches) != 1 or matches[0]['question'] != question.get('question'):
        raise ContractError('Question is outside the reviewed snapshot')
    return _literal_contract(question)

def validate_contract(contract, question):
    import jsonschema
    schema = json.loads((HERE / 'schema.json').read_text())
    try:
        jsonschema.Draft202012Validator(schema).validate(contract)
    except jsonschema.ValidationError as e:
        raise ContractError(str(e)) from e
    expected = build_contract(question)
    if contract != expected:
        raise ContractError('Contract facts, anchors, identity or unknown boundaries differ from reviewed transcription')
    return True

def consumer_view(contract, question):
    """Pure candidate adapter; refuses legacy tier backfill even if metadata has one."""
    validate_contract(contract, question)
    return {'question_id': question['question_id'],
            'samples_by_id': {s['sample_id']: deepcopy(s) for s in contract['samples']},
            'cross_sample_aggregation': 'UNKNOWN', 'time': 'UNKNOWN', 'ri': 'UNKNOWN',
            'legacy_scalar_backfill_allowed': False, 'scientific_scoring_ready': False}

def bind_answer_sample_ids(contract, question, answer_sample_ids):
    """Exact IDs only. No fuzzy mapping of 'main', a tissue string, or merged IDs."""
    view = consumer_view(contract, question)
    if len(answer_sample_ids) != len(set(answer_sample_ids)):
        raise ContractError('Duplicate answer sample id')
    if set(answer_sample_ids) != set(view['samples_by_id']):
        raise ContractError('Answer object coverage does not equal reviewed sample scope')
    return {sid: deepcopy(view['samples_by_id'][sid]) for sid in answer_sample_ids}

def aggregate_samples(*args, **kwargs):
    raise ContractError('Cross-sample aggregation is UNKNOWN; no sum/max/mean or shared tier is authorized')
