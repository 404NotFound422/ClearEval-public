"""Closed-world, reviewed transcription consumer. Never a model extractor."""
import json
import hashlib
import sys
from copy import deepcopy
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'contract'))
from contract import SUPPORTED, VERSION, ContractError, validate_contract, consumer_view

class ScopeRegistry:
    def __init__(self, path=None):
        self.path = Path(path or HERE.parent / 'contract/fixtures/contracts.json')
        rows = json.loads(self.path.read_text())
        if not isinstance(rows, list) or len(rows) != len(SUPPORTED):
            raise ContractError('Sidecar must contain exactly nine reviewed records')
        self.rows = {r['question_id']: r for r in rows}
        if len(self.rows) != len(rows) or set(self.rows) != SUPPORTED:
            raise ContractError('Duplicate, missing or foreign sidecar question')
        approved = json.loads((HERE.parent / 'contract/fixtures/questions.json').read_text())
        for q in approved:
            validate_contract(self.rows[q['question_id']], q)
        self.sha256 = hashlib.sha256(self.path.read_bytes()).hexdigest()

    @staticmethod
    def is_protected(qid):
        return qid in SUPPORTED

    def _assert_current(self):
        if getattr(self, 'load_error', None):
            raise ContractError('Protected sample scope unavailable: ' + self.load_error)
        try:
            current = hashlib.sha256(self.path.read_bytes()).hexdigest()
        except OSError as exc:
            raise ContractError('Protected sidecar unavailable; cached scope cannot be reused') from exc
        if current != self.sha256:
            raise ContractError('Protected sidecar changed; restart and revalidate snapshot')

    def view(self, question):
        if question['question_id'] not in SUPPORTED:
            return None
        self._assert_current()
        result = consumer_view(self.rows[question['question_id']], question)
        result.update(schema_version=VERSION, sidecar_sha256=self.sha256,
                      provenance='MANUALLY_REVIEWED_CLOSED_WORLD_TRANSCRIPTION')
        return result

    def validate_snapshot(self, questions, unavailable_ok=False):
        ids = [q['question_id'] for q in questions]
        if len(ids) != len(set(ids)):
            raise ContractError('Duplicate snapshot question')
        for q in questions:
            if unavailable_ok and getattr(self, "load_error", None):
                continue
            self.view(q)

    def metadata(self, question, unavailable_ok=False):
        if (unavailable_ok and getattr(self, 'load_error', None)
                and self.is_protected(question['question_id'])):
            return {'sample_scope': None, 'sample_scope_status': 'UNAVAILABLE',
                    'tissue_tier_code': 'UNKNOWN', 'tissue_inferred': 'UNKNOWN',
                    'tissue_ri_value': None,
                    'tissue_ri_reference': {'status': 'UNKNOWN', 'value': None},
                    'marker_query_targets': question.get('marker_query_targets', [])}
        view = self.view(question)
        if view is None:
            return None
        return {'sample_scope': view, 'tissue_tier_code': 'UNKNOWN',
                'tissue_inferred': 'UNKNOWN', 'tissue_ri_value': None,
                'tissue_ri_reference': {'status': 'UNKNOWN', 'value': None,
                                        'reason': 'PER_OBJECT_REFERENCE_NOT_REVIEWED'},
                'marker_query_targets': question.get('marker_query_targets', [])}

    def unresolved(self, question):
        view = self.view(question)
        if view is None:
            return None
        return {'question_id': question['question_id'], 'sample_scope': view,
                'technical_status': 'VALID', 'scientific_status': 'UNRESOLVED',
                'cce_eligible': False, 'official_scores': None,
                'sample_results': {sid: {'identity': s['identity'], 'form': s['form'],
                    'tier': 'UNKNOWN', 'reference_applicability': 'UNKNOWN',
                    'time_reference': 'UNKNOWN', 'ri_reference': 'UNKNOWN',
                    'scientific_status': 'UNKNOWN', 'scores': None}
                    for sid, s in view['samples_by_id'].items()},
                'answer_object_binding': 'UNRESOLVED', 'cross_sample_aggregation': 'UNKNOWN',
                'reason': 'NO_REVIEWED_PER_OBJECT_SCIENTIFIC_REFERENCE'}

    def card(self, question, binding):
        view = self.view(question)
        if view is None:
            return None
        from evaluation_contract import json_hash
        card = {'question_id': question['question_id'], 'input_binding': binding,
                'sample_scope': view, 'knowledge_status': 'PER_OBJECT_REFERENCE_UNKNOWN',
                'scenario_slot_card': {'samples_by_id': view['samples_by_id'],
                                       'sample_tier_code': 'UNKNOWN'},
                'candidate_method_cards': [], 'method_mini_index': [],
                'target_marker_cards': [], 'compatibility_records': [],
                'feasibility_card': {'status': 'UNKNOWN'},
                'sample_reference_cards': {sid: {'identity': s['identity'], 'form': s['form'],
                    'reference_applicability': 'UNKNOWN', 'references': []}
                    for sid, s in view['samples_by_id'].items()},
                'prompt_block': 'Reviewed question-local objects:\n' + '\n'.join(
                    f"{sid}: {s['identity']} ({s['form']}); tier/reference/time/RI UNKNOWN."
                    for sid, s in view['samples_by_id'].items()) +
                    '\nNo shared tissue reference or cross-object aggregation is authorized.'}
        card['card_content_sha256'] = json_hash(card)
        return card

    def prepare_write(self, obj, questions):
        snapshot = {q['question_id']: q for q in questions}
        def visit(value):
            if isinstance(value, list):
                return [visit(x) for x in value]
            if not isinstance(value, dict):
                return value
            result = {k: visit(v) for k, v in value.items()}
            qid = value.get('question_id')
            if qid in SUPPORTED:
                if qid not in snapshot:
                    raise ContractError('Output question absent from active snapshot')
                q = snapshot[qid]
                expected = self.unresolved(q)
                for key in ('sample_scope', 'sample_results'):
                    if key in value and value[key] != expected[key]:
                        raise ContractError('Output sample identity or result mismatch: ' + key)
                # Nested legacy tissue metadata is not an alternate identity channel.
                result.pop('tissue_hierarchy_from_tissue_xlsx', None)
                if 'specific_question' in value and value['specific_question'] != q['question']:
                    raise ContractError('Output question text mismatch')
                for key in ('scores', 'official_scores', 'benchmark_scores', 'aggregate_score',
                            'calculated_scores', 'legacy_diagnostics', 'benchmark_estimate', 'aggregate_scores'):
                    if value.get(key) is not None:
                        raise ContractError('Cannot write unreviewed sample-scope scores: ' + key)
                if 'evaluation' in value:
                    result['evaluation'] = self.unresolved(q)
                result.update(self.metadata(q))
            return result
        return visit(deepcopy(obj))

try:
    SCOPE = ScopeRegistry()
except (OSError, ValueError, KeyError, TypeError) as exc:
    # Loading a non-target consumer must remain possible. Protected IDs remain
    # denied until the exact sidecar and reviewed snapshot validate on restart.
    SCOPE = ScopeRegistry.__new__(ScopeRegistry)
    SCOPE.path = HERE.parent / 'contract/fixtures/contracts.json'
    SCOPE.rows = {}
    SCOPE.sha256 = 'UNAVAILABLE'
    SCOPE.load_error = type(exc).__name__ + ': ' + str(exc)

