"""Versioned question/table contract. Recommendation metadata never grants necessity.

This module does not score biology or edit archived inputs. A future generator
must supply reviewed requirement expressions and validate before publishing.
"""
from copy import deepcopy
from pathlib import Path
import ast
import csv
import hashlib
import json
import re
import unicodedata
from verified_marker_aliases import same_verified_target

VERSION = 'marker-input-contract-v1'
ROOT = Path(__file__).resolve().parent
AUDIT = ROOT / 'experiments/archived_marker_input_audit_20261015/all_target_rows.csv'


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()


def normalize_tables(value):
    if isinstance(value, str):
        value = ast.literal_eval(value)
    if not isinstance(value, dict):
        raise ValueError('Actual supplied restriction tables must be an object')
    result = {}
    for key, entries in value.items():
        if not isinstance(entries, (list, tuple, set)) or not all(isinstance(x, str) for x in entries):
            raise ValueError('Restriction entries must be strings')
        result[key] = [s.strip() for x in sorted(entries) if isinstance(entries, set) for s in x.split('、')] if isinstance(entries, set) else [s.strip() for x in entries for s in x.split('、')]
    return result


def _norm(value):
    return re.sub(r'[^\wα-ω]', '', unicodedata.normalize('NFKC', value).casefold())


def marker_availability(name, tables):
    """Identity only. Never infer HEV from CD31 or PNA from generic Lectin."""
    entries = [(section, entry) for section in ('Marker', 'Dye_or_Fluorophore')
               for entry in tables.get(section, [])]
    for section, entry in entries:
        if _norm(name) == _norm(entry) or same_verified_target(name, entry):
            return {'status': 'AVAILABLE', 'section': section, 'entry': entry,
                    'identity_scope': 'IDENTITY_ONLY_NOT_FUNCTIONAL_EQUIVALENCE'}
        # Only literal whole listed labels/components; no inferred family members.
        components = [s.strip() for s in re.split(r'\s+/\s+|[()（）]', entry) if s.strip()]
        if _norm(name) in {_norm(s) for s in components}:
            return {'status': 'AVAILABLE', 'section': section, 'entry': entry,
                    'identity_scope': 'LITERAL_LISTED_COMPONENT_ONLY'}
    return {'status': 'NOT_CONFIRMED_AVAILABLE', 'section': None, 'entry': None}


def generation_input_from_entry(entry):
    """Read the actual archived prompt; never substitute today's DEFAULT_RESTRICT."""
    if not isinstance(entry.get('prompt'), str) or 'restrictions' not in entry:
        return None
    return {'prompt': entry['prompt'], 'restrictions': deepcopy(entry['restrictions']),
            'origin': 'ACTUAL_ARCHIVED_GENERATION_INPUT'}


def _audited_rows(question, tables):
    if not AUDIT.exists():
        return {}
    result = {}
    with AUDIT.open(encoding='utf-8', newline='') as source:
        for row in csv.DictReader(source):
            if row['question_id'] != str(question.get('question_id')) or row['original_question'] != question.get('question'):
                continue
            if row['marker_table_original'].split('、') != tables.get('Marker') or row['dye_table_original'].split('、') != tables.get('Dye_or_Fluorophore'):
                continue
            result[row['metadata_path']] = row
    return result


def build_marker_input_contract(question_meta, generation_input=None):
    original = deepcopy(question_meta.get('marker_query_targets') or [])
    text = str(question_meta.get('question', ''))
    tables, actual_prompt = {}, None
    if generation_input is not None:
        tables = normalize_tables(generation_input['restrictions'])
        actual_prompt = generation_input['prompt']
        if not isinstance(actual_prompt, str) or text not in actual_prompt:
            raise ValueError('Actual generation prompt must contain the unchanged question')
        for section, entries in tables.items():
            match = re.search(re.escape(section) + r':\{([^}]+)\}', actual_prompt)
            if not match or match[1].split('、') != entries:
                raise ValueError('Actual prompt/restriction table mismatch: ' + section)
    reviewed = _audited_rows(question_meta, tables)
    candidates, issues = [], []
    for i, target in enumerate(original):
        path = f'marker_query_targets/{i}'
        name = target.get('marker_name', target.get('name', ''))
        availability = marker_availability(name, tables) if tables else {'status': 'ACTUAL_TABLE_UNAVAILABLE'}
        row = reviewed.get(path)
        if row and row['marker_name'] != name:
            raise ValueError('Archived audit target binding mismatch')
        reading = row['requirement_reading'] if row else 'REFERENCE_CANDIDATE_NOT_REQUIRED_BY_METADATA'
        requiredness = 'REFERENCE_CANDIDATE_ONLY'
        if reading == 'EXPLICIT_NAMED_TARGET_REQUIRED':
            requiredness = 'EXPLICIT_QUESTION_REQUIREMENT'
        elif reading == 'EXPLICIT_ALTERNATIVE_ROUTE_NOT_GLOBAL_REQUIREMENT':
            requiredness = 'ALTERNATIVE_ROUTE_MEMBER_NOT_GLOBALLY_REQUIRED'
        elif reading == 'COMPOSITE_METADATA_WITH_EXPLICIT_REQUIRED_COMPONENT':
            requiredness = 'COMPOSITE_REQUIRES_COMPONENT_LEVEL_REVIEW'
        if row:
            availability['archived_audit_status'] = row['status']
            availability['component_matches'] = json.loads(row['component_matches_json'])
        candidates.append({'metadata_path': path, 'original_metadata': target,
            'availability': availability, 'requiredness': requiredness,
            'requiredness_source': 'QUESTION_TEXT_REVIEW' if requiredness != 'REFERENCE_CANDIDATE_ONLY' else 'METADATA_IS_RECOMMENDATION_ONLY',
            'absence_penalty_from_metadata': False, 'archived_question_reading': reading,
            'requiredness_scope': 'METADATA_ROLE_ANNOTATION_NOT_EXHAUSTIVE_QUESTION_REQUIREMENT_PARSE'})
        if row and row['missing_components'] and requiredness == 'EXPLICIT_QUESTION_REQUIREMENT':
            issues.append({'code': 'EXPLICIT_TARGET_UNAVAILABLE_IN_SUPPLIED_TABLE', 'target': name,
                'metadata_path': path, 'constraint_explicit': '不引入给定标记物列表之外靶点' in text,
                'issue_kind': 'CONFIRMED_CLOSED_LIST_CONFLICT' if '不引入给定标记物列表之外靶点' in text else 'EXPLICIT_TARGET_TABLE_GAP_SCOPE_REVIEW',
                'attribution': 'QUESTION_TABLE_DATA_ISSUE_NOT_ANSWER_FAILURE'})
    # HEV is a functional identity requirement, not a synonym of PNAd or CD31.
    if reviewed and '对应的表内 HEV 标记靶点' in text:
        pnad = [c for c in candidates if c['original_metadata'].get('marker_name') == 'PNAd']
        if pnad and pnad[0]['availability'].get('archived_audit_status') == 'ABSENT_AFTER_LOCAL_CHECKS':
            issues.append({'code': 'EXPLICIT_HEV_FUNCTION_WITHOUT_VERIFIED_SUPPLIED_ROUTE',
                'target': 'HEV-specific identity', 'constraint_explicit': True,
                'issue_kind': 'EXPLICIT_HEV_FUNCTION_TABLE_GAP',
                'attribution': 'QUESTION_TABLE_DATA_ISSUE_NOT_ANSWER_FAILURE',
                'note': 'PNAd is an unavailable reference candidate; CD31/nuclear signal is not verified HEV specificity.'})
    return {'schema_version': VERSION, 'question_sha256': _hash(question_meta),
        'actual_generation_input_status': 'BOUND' if generation_input is not None else 'UNAVAILABLE_DO_NOT_ASSUME_CURRENT_TABLE',
        'actual_prompt_sha256': hashlib.sha256(actual_prompt.encode()).hexdigest() if actual_prompt is not None else None,
        'actual_question': text, 'actual_supplied_tables': tables,
        'reference_candidates': candidates, 'data_issues': issues,
        'archived_review_sha256': hashlib.sha256(AUDIT.read_bytes()).hexdigest() if reviewed else None,
        'evaluation_policy': {'obligations_source': 'ACTUAL_QUESTION_AND_SUPPLIED_TABLE_ONLY',
            'metadata_may_create_mandatory_targets': False,
            'nonreference_marker_penalty': 'NONE_SOLELY_FOR_NONREFERENCE_STATUS',
            'scientific_applicability': 'ASSESS_ACTUAL_FUNCTION_SPECIES_TISSUE_AND_METHOD_SEPARATELY',
            'inconsistent_input': 'EXPOSE_DATA_ISSUE_DO_NOT_ATTRIBUTE_UNAVAILABLE_REQUIREMENT_TO_ANSWER',
            'alternatives': 'PRESERVE_OR_AND_VIABLE_ROUTES_NO_ALL_MEMBERS_REQUIREMENT'}}


def validate_generation_contract(question, tables, requirement_formula):
    """Validate a reviewed all/any expression BEFORE generating a future prompt.

    Leaves: {marker: exact supplied identity, question_quote: literal evidence}.
    A function may list reviewed alternatives as any leaves, never synonyms.
    Recommendations are not automatically included. Unavailable optional OR
    leaves are reported without vetoing a viable route. No table is expanded.
    """
    tables = normalize_tables(tables)
    unavailable = []
    def visit(node):
        if not isinstance(node, dict):
            raise ValueError('Requirement expression must be an object')
        if set(node) == {'marker', 'question_quote'}:
            if not isinstance(node['question_quote'], str) or not node['question_quote'] or node['question_quote'] not in question:
                raise ValueError('Every requirement needs actual question evidence')
            status = marker_availability(node['marker'], tables)['status'] == 'AVAILABLE'
            if not status:
                unavailable.append(node['marker'])
            return status
        if len(node) != 1 or next(iter(node)) not in ('all', 'any'):
            raise ValueError('Only explicit all/any requirement composition is supported')
        op, children = next(iter(node.items()))
        if not isinstance(children, list) or not children:
            raise ValueError('Requirement groups must be nonempty')
        values = [visit(child) for child in children]
        return all(values) if op == 'all' else any(values)
    viable = visit(requirement_formula)
    if not viable:
        raise ValueError('UNSUPPLIED_MANDATORY_TARGET: no viable route in supplied table; revise reviewed question or table before publication')
    return {'schema_version': VERSION, 'publishable': True, 'requirement_formula': deepcopy(requirement_formula),
            'unavailable_alternative_members': unavailable, 'tables_sha256': _hash(tables),
            'scope': 'TABLE_AVAILABILITY_ONLY_FUNCTIONAL_ROUTE_REVIEW_STILL_REQUIRED'}


def generate_validated_question_packet(question_meta, tables, requirement_formula):
    """Single-source future input builder; does not mutate the question or table."""
    tables = normalize_tables(tables)
    validation = validate_generation_contract(question_meta['question'], tables, requirement_formula)
    table_text = '\n'.join(key + ':{' + '、'.join(values) + '}' for key, values in tables.items())
    prompt = question_meta['question'] + '\n**restrctions**\n' + table_text
    generation_input = {'prompt': prompt, 'restrictions': tables, 'origin': 'VALIDATED_SINGLE_SOURCE_GENERATOR'}
    return {'question_meta': deepcopy(question_meta), 'generation_input': generation_input,
            'validation': validation, 'marker_input_contract': build_marker_input_contract(question_meta, generation_input)}


def bind_entry_study(question, entry, study=None):
    generation_input = generation_input_from_entry(entry)
    if generation_input is None:
        return deepcopy(study)
    result = deepcopy(study) if study is not None else {
        'question_sha256': _hash(question),
        'protocol_sha256': hashlib.sha256(entry['model_response'].encode()).hexdigest()}
    if result.get('generation_input') not in (None, generation_input):
        raise ValueError('Frozen study generation input differs from actual answer entry')
    result['generation_input'] = generation_input
    return result


def validate_upstream_question_contract(question_meta, tables):
    """The real generator gate: metadata alone is never a requirements manifest."""
    formula = question_meta.get('marker_requirement_formula')
    if formula is None:
        normalized = normalize_tables(tables)
        rendered = question_meta['question'] + '\n' + '\n'.join(k + ':{' + '、'.join(v) + '}' for k, v in normalized.items())
        contract = build_marker_input_contract(question_meta, {'prompt': rendered, 'restrictions': normalized})
        # A missing reference candidate cannot prove that every functional route is unavailable.
        # Only explicitly named required identities plus an explicit closed list establish this conflict.
        conflicts = [issue for issue in contract['data_issues']
                     if issue.get('issue_kind') == 'CONFIRMED_CLOSED_LIST_CONFLICT']
        if conflicts:
            raise ValueError('EXPLICIT_QUESTION_TABLE_CONFLICT: ' + ', '.join(issue['code'] for issue in conflicts))
        return {'schema_version': VERSION, 'publishable': True,
                'scope': 'ADVISORY_METADATA_ONLY_NO_NEW_MANDATORY_TARGETS',
                'warning': 'No declared marker formula; recommendation metadata is not a mandatory target list.'}
    return validate_generation_contract(question_meta['question'], tables, formula)
