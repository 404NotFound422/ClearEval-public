"""Self-contained engineering fixtures: no archive raw, model, encoder or scores.

Run with the candidate source and its unchanged vendor snapshot available:
  python -m unittest discover -s tests -p test_scope_regressions.py -v
These literal strings test parser/gate behavior, not biological correctness.
"""
import copy
import pathlib
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import runner as R
from experiments.construct_validity.compact_grounding import build_record_catalog
from oeq_atomic_alignment import (
    UNKNOWN, annotate, candidate_from_records, eligibility, execution_status,
    heading_scope_evidence, pair_scope,
)
from oeq_capacity_matching import identity_relation
from oeq_simple_representation import from_catalog, operation_record


def literal_fixture(protocol, selected=True):
    catalog = build_record_catalog(protocol)
    extraction = {
        'branches': [{'id': 'main', 'mode': 'SERIAL', 'spans': []}],
        'steps': [{'id': r['record_id'], 'branch': 'main', 'assertion': r['assertion']}
                  for r in catalog['records']] if selected else [],
    }
    return catalog, extraction, from_catalog(protocol, catalog, extraction)


def scoped_fixture(protocol, selected=True):
    catalog, extraction, candidate = literal_fixture(protocol, selected)
    reference = {'operations': annotate([operation_record(
        'Incubate in DCM.', record_id='ENGINEERING_REFERENCE', phase='Clearing')])}
    pair = pair_scope(candidate_from_records(candidate), reference,
                      'requested_clearing', method='iDISCO+')
    return catalog, extraction, pair


def consume_pair(protocol, catalog, extraction, pair):
    """Test the actual runner gate, isolating only upstream source providers."""
    case = {
        'protocol': protocol, 'question': {}, 'task_evidence': {},
        'reference': {'constructor': 'reviewed_atomic', 'source_id': 'ENGINEERING_ONLY'},
        'evaluation_object': {'route_id': 'main'},
    }
    with patch('oeq_practical_assessment._check_source', return_value={}), \
         patch('oeq_practical_assessment._build_pair', return_value=copy.deepcopy(pair)), \
         patch('oeq_practical_assessment._paired_inventory', return_value={}):
        return R.pair_inputs(case, {'catalog': catalog}, {'extraction': extraction})


class ScopeRegressionTests(unittest.TestCase):
    def test_known_preparation_heading_excluded_without_disabling_gate(self):
        protocol = '# Bleaching and Rehydration\n1. Incubate in methanol.\n# Clearing\n2. Incubate in DCM.'
        catalog, extraction, pair = scoped_fixture(protocol)
        self.assertEqual(len(pair['candidate']['operations']), 1)
        self.assertEqual(len(pair['candidate']['excluded_operations']), 1)
        self.assertEqual(pair['candidate']['unresolved_scope_operations'], [])
        self.assertEqual(pair['candidate']['excluded_operations'][0]['comparison_phase'], 'pretreatment')
        self.assertEqual(len(consume_pair(protocol, catalog, extraction, pair)[0]['candidate']['original_scoped_rows']), 1)

    def test_outside_scope_membership_preserves_phase_uncertainty(self):
        protocol = '# Pre-treatment and Permeabilization\n1. Incubate in permeabilization solution.\n# Clearing\n2. Incubate in DCM.'
        catalog, extraction, pair = scoped_fixture(protocol)
        excluded = pair['candidate']['excluded_operations'][0]
        self.assertEqual(excluded['comparison_phase'], UNKNOWN)
        self.assertEqual(set(excluded['comparison_phase_candidates']), {'pretreatment', 'immunolabeling'})
        self.assertTrue(excluded['scope_membership_evidence']['phase_uncertainty_preserved'])
        self.assertEqual(excluded['scope_membership_evidence']['status'], 'DEFINITELY_OUTSIDE_REQUESTED_SCOPE')
        consume_pair(protocol, catalog, extraction, pair)

    def test_unknown_current_heading_remains_technical_blocker(self):
        protocol = '# Unreviewed Processing\n1. Incubate in DCM.'
        catalog, extraction, pair = scoped_fixture(protocol)
        self.assertEqual(pair['candidate']['operations'], [])
        with self.assertRaisesRegex(R.InputUnsupported, 'INPUT_SCOPE_UNSUPPORTED') as caught:
            consume_pair(protocol, catalog, extraction, pair)
        self.assertEqual(len(caught.exception.details['unresolved_rows']), 1)
        self.assertNotIn('score', caught.exception.details)

    def test_in_scope_outside_scope_conflict_still_blocks(self):
        protocol = '# Clearing\n1. Incubate with primary antibody.'
        catalog, extraction, pair = scoped_fixture(protocol)
        row = pair['candidate']['unresolved_scope_operations'][0]
        self.assertEqual(set(row['comparison_phase_candidates']), {'clearing', 'immunolabeling'})
        with self.assertRaises(R.InputUnsupported):
            consume_pair(protocol, catalog, extraction, pair)

    def test_explicit_mixed_scope_heading_does_not_choose_first_phase(self):
        for heading in ['Pretreatment and clearing', 'Clearing and pretreatment',
                        'Immunolabeling and dehydration', 'Dehydration / immunolabeling',
                        'Pre-treatment and Dehydration']:
            with self.subTest(heading=heading):
                protocol = '# ' + heading + '\n1. Incubate in methanol.'
                catalog, extraction, pair = scoped_fixture(protocol)
                self.assertEqual(pair['candidate']['operations'], [])
                self.assertEqual(pair['candidate']['excluded_operations'], [])
                with self.assertRaises(R.InputUnsupported):
                    consume_pair(protocol, catalog, extraction, pair)

    def test_source_backed_solvent_reversal_allows_equal_boundary_wash(self):
        protocol = ('# Pre-treatment and Dehydration\n'
                    '1. Wash in PBS to remove residual fixative.\n'
                    '2. Incubate in 20% methanol.\n'
                    '3. Incubate in 100% methanol.\n'
                    '# Bleaching and Rehydration\n'
                    '4. Incubate in 5% H2O2 in methanol.\n'
                    '5. Incubate in 100% methanol.\n'
                    '6. Incubate in 80% methanol.\n'
                    '7. Incubate in 20% methanol.\n'
                    '# Clearing\n8. Incubate in DCM.')
        catalog, extraction, pair = scoped_fixture(protocol)
        self.assertEqual(pair['candidate']['unresolved_scope_operations'], [])
        self.assertEqual(len(pair['candidate']['operations']), 1)
        anchors = [r['scope_context_evidence'] for r in pair['candidate']['excluded_operations'] if 'scope_context_evidence' in r]
        self.assertTrue(anchors)
        self.assertEqual(anchors[0]['ascending_concentrations'], [20., 100.])
        self.assertEqual(anchors[0]['descending_concentrations'], [100., 80., 20.])
        self.assertFalse(anchors[0]['unreported_steps_inferred'])
        consume_pair(protocol, catalog, extraction, pair)
        # Missing or optional bleach is not evidence of an observed sequence.
        for replacement in ['Incubate in sucrose.', 'Optional: incubate in 5% H2O2 in methanol.',
                            'Do not incubate in 5% H2O2 in methanol.']:
            altered = protocol.replace('Incubate in 5% H2O2 in methanol.', replacement)
            c, e, p = scoped_fixture(altered)
            with self.assertRaises(R.InputUnsupported):
                consume_pair(altered, c, e, p)

    def test_solvent_reversal_does_not_cross_routes_or_override_clearing(self):
        protocol = ('# Pre-treatment and Dehydration\n'
                    '1. Incubate in 20% methanol.\n2. Incubate in 100% methanol.\n'
                    '# Bleaching and Rehydration\n'
                    '3. Incubate in 5% H2O2 in methanol.\n'
                    '4. Incubate in 100% methanol.\n5. Incubate in 80% methanol.\n')
        flat = protocol.replace('80% methanol.', '100% methanol.')
        c, e, p = scoped_fixture(flat)
        with self.assertRaises(R.InputUnsupported):
            consume_pair(flat, c, e, p)
        for heading in ['Clearing', 'Optical Clearing', 'Final Clearing', '透明化',
                        '脱脂/透明化', 'Dehydration (after labeling)']:
            altered = protocol.replace('Pre-treatment and Dehydration', heading)
            c, e, p = scoped_fixture(altered)
            with self.assertRaises(R.InputUnsupported):
                consume_pair(altered, c, e, p)
            for row in p['candidate']['unresolved_scope_operations']:
                if 'scope_context_evidence' in row:
                    self.assertEqual(row['scope_context_evidence']['interpretation'], 'CONFLICTING_EXPLICIT_FINAL_HEADING')
        catalog, extraction, representation = literal_fixture(protocol)
        representation['operations'][2]['branch'] = 'other'
        reference = {'operations': annotate([operation_record('Incubate in DCM.', record_id='R', phase='Clearing')])}
        pair = pair_scope(candidate_from_records(representation), reference, 'requested_clearing', method='iDISCO+')
        with self.assertRaises(R.InputUnsupported):
            consume_pair(protocol, catalog, extraction, pair)

    def test_unknown_reference_phase_still_blocks(self):
        protocol = '# Clearing\n1. Incubate in DCM.'
        catalog, extraction, pair = scoped_fixture(protocol)
        unknown = annotate([operation_record('Incubate in DCM.', record_id='UNKNOWN_REFERENCE', phase='Unknown')])[0]
        pair['reference']['unresolved_scope_operations'] = [unknown]
        with self.assertRaises(R.InputUnsupported) as caught:
            consume_pair(protocol, catalog, extraction, pair)
        self.assertEqual(caught.exception.details['unresolved_rows'][0]['side'], 'reference')

    def test_unselected_route_does_not_block_requested_route(self):
        protocol = '# Clearing\n1. Incubate in DCM.'
        catalog, extraction, pair = scoped_fixture(protocol)
        unknown = annotate([operation_record('Incubate in DCM.', record_id='FOREIGN', phase='Unknown', branch='other')])[0]
        pair['candidate']['unresolved_scope_operations'] = [unknown]
        result = consume_pair(protocol, catalog, extraction, pair)[0]
        self.assertEqual(len(result['candidate']['original_scoped_rows']), 1)
        self.assertEqual(result['candidate']['unresolved_scope_operations'][0]['branch'], 'other')

    def test_chinese_negated_optional_and_unselected_rows_not_asserted(self):
        for body, status in [
            ('不要在 DCM 中孵育。', 'PROHIBITED_OR_OMITTED'),
            ('无需在 DCM 中孵育。', 'PROHIBITED_OR_OMITTED'),
            ('可选：在 DCM 中孵育。', 'OPTIONAL_OR_CONDITIONAL'),
            ('如果需要，在 DCM 中孵育。', 'OPTIONAL_OR_CONDITIONAL'),
        ]:
            for selected in (True, False):
                with self.subTest(body=body, selected=selected):
                    protocol = '# 未支持阶段\n1. ' + body
                    catalog, extraction, pair = scoped_fixture(protocol, selected)
                    row = pair['candidate']['unresolved_scope_operations'][0]
                    self.assertEqual(execution_status(row), status)
                    self.assertEqual(row['raw_text'], '1. ' + body)
                    consume_pair(protocol, catalog, extraction, pair)
        protocol = '# 未支持阶段\n1. Incubate in DCM.'
        catalog, extraction, pair = scoped_fixture(protocol, selected=False)
        self.assertEqual(execution_status(pair['candidate']['unresolved_scope_operations'][0]), 'UNRESOLVED_SELECTION')
        consume_pair(protocol, catalog, extraction, pair)

    def test_finite_chinese_current_headings_preserve_original_text(self):
        headings = [
            ('预处理与脱色（用于后续透明化）', 'pretreatment'),
            ('渗透/封闭（为全身免疫标记做准备）', 'immunolabeling'),
            ('全身免疫标记（辅助确认）', 'immunolabeling'),
            ('核染（单细胞判读）', 'immunolabeling'),
            ('FDISCO脱水（低温、分级）', 'clearing'),
            ('脱脂/进一步透明化（FDISCO关键步骤）', 'clearing'),
            ('RI匹配（最终透明与成像介质）', 'ri_matching_storage'),
            ('保存与成像前处理（降低背景）', 'ri_matching_storage'),
        ]
        for heading, phase in headings:
            with self.subTest(heading=heading):
                protocol = '# ' + heading + '\n1. Incubate in DCM.'
                _, _, rep = literal_fixture(protocol)
                row = annotate(rep['operations'])[0]
                self.assertEqual(row['comparison_phase'], phase)
                self.assertEqual(row['phase'], '# ' + heading)
                self.assertEqual(rep['source_sha256'], R.text_sha(protocol))

    def test_future_purpose_cannot_promote_current_phase(self):
        for heading in ['Preparation for refractive index matching',
                        'Dehydration for immunolabeling',
                        'Preparation for clearing and RI matching']:
            with self.subTest(heading=heading):
                protocol = '# ' + heading + '\n1. Incubate in DCM.'
                catalog, extraction, pair = scoped_fixture(protocol)
                self.assertEqual(pair['candidate']['operations'], [])
                self.assertEqual(len(pair['candidate']['unresolved_scope_operations']), 1)
                with self.assertRaises(R.InputUnsupported):
                    consume_pair(protocol, catalog, extraction, pair)
        for heading in ['Pretreatment for subsequent clearing', '预处理（用于之后的透明化）']:
            evidence = heading_scope_evidence(heading)
            self.assertEqual(evidence['phase'], 'pretreatment')
            self.assertFalse(evidence['future_context_promoted'])
        self.assertEqual(heading_scope_evidence('Clearing (after labeling)')['phase'], 'clearing')

    def test_mixed_and_unknown_heading_suffixes_remain_unresolved(self):
        for heading in ['透明化与免疫标记', 'RI实验性未知阶段',
                        'Clearing (for imaging) and immunolabeling',
                        'Clearing (unclosed note']:
            with self.subTest(heading=heading):
                self.assertEqual(heading_scope_evidence(heading)['phase'], UNKNOWN)

    def test_explicit_post_label_buffer_washes_are_outside_clearing(self):
        for heading, operation in [
            ('Post-staining Wash', 'Incubation with PBT.'),
            ('Post-staining Washes', 'Wash with PTx + 10% DMSO.'),
            ('Wash After Primary（主抗后清洗）', 'PTwH 振荡清洗。'),
            ('Wash After Secondary', 'Wash with PTwH buffer.'),
        ]:
            with self.subTest(heading=heading):
                protocol = '# ' + heading + '\n1. ' + operation
                catalog, extraction, pair = scoped_fixture(protocol)
                self.assertEqual(len(pair['candidate']['excluded_operations']), 1)
                self.assertEqual(pair['candidate']['excluded_operations'][0]['comparison_phase'], 'immunolabeling')
                consume_pair(protocol, catalog, extraction, pair)

    def test_generic_wash_and_contradictory_post_label_wash_stay_unresolved(self):
        for protocol in [
            '# Wash\n1. Wash with PBT.',
            '# Primary Labeling\n1. Incubate with primary antibody.\n# Wash\n2. Wash with PBT.',
            '# Post-staining Wash\n1. Incubate in DCM.',
            '# Post-staining Wash\n1. Wash with PBT for clearing.',
            '# Post-staining Wash\n1. Repeat step 7.2 five times.',
        ]:
            with self.subTest(protocol=protocol):
                catalog, extraction, pair = scoped_fixture(protocol)
                self.assertTrue(pair['candidate']['unresolved_scope_operations'])
                with self.assertRaises(R.InputUnsupported):
                    consume_pair(protocol, catalog, extraction, pair)

    def test_verified_v3_assertion_compatibility_retains_assertion(self):
        for body, status in [
            ('Incubate in DCM.', 'ASSERTED_OPERATION'),
            ('不要在 DCM 中孵育。', 'PROHIBITED_OR_OMITTED'),
            ('Incubate in DCM（时间：2 h；备注：after labeling）', 'UNRESOLVED_SELECTION'),
        ]:
            with self.subTest(body=body):
                protocol = '# Clearing\n1. ' + body
                catalog, extraction, _ = literal_fixture(protocol)
                extraction['steps'][0]['assertion'] = copy.deepcopy(extraction['steps'][0]['assertion'])
                extraction['steps'][0]['assertion']['scope_policy'] = 'bounded-directive-scope-v3-procedural-adjuncts'
                row = from_catalog(protocol, catalog, extraction)['operations'][0]
                self.assertEqual(execution_status(row), status)
                self.assertTrue(row['assertion_compatibility_audit']['source_assertion_revalidated'])
                tampered = copy.deepcopy(extraction)
                tampered['steps'][0]['assertion']['record_span']['quote'] += ' invented'
                with self.assertRaises(ValueError):
                    from_catalog(protocol, catalog, tampered)

    def test_unknown_identity_never_matches_merely_because_both_unknown(self):
        for left, right in [('Incubate in sucrose.', 'Incubate in formamide.'),
                            ('Incubate in CUBIC-L.', 'Incubate in CUBIC-R.')]:
            relation = identity_relation({'operation': left}, {'operation': right})
            self.assertEqual(relation['status'], 'UNRESOLVED')
            self.assertEqual(relation['chemical_identity_status'], 'UNRESOLVED')
            self.assertNotEqual(relation['reason'], 'explicit_reagent_identity_conflict')

    def test_literal_identity_exception_does_not_relax_modality_or_parameters(self):
        a = operation_record('1. Incubate in sucrose (Time: 2 h).', record_id='R', phase='Clearing')
        b = operation_record('2. Incubate  in sucrose (Time: 2 h).', record_id='G', phase='Clearing')
        relation = identity_relation(a, b)
        self.assertEqual(relation['basis'], 'EXACT_OPERATION_TEXT')
        self.assertEqual(relation['chemical_identity_status'], 'UNRESOLVED')
        changed = dict(b, raw_text=b['raw_text'].replace('2 h', '3 h'))
        self.assertEqual(identity_relation(a, changed)['status'], 'UNRESOLVED')
        nonasserted = dict(b, assertion={'polarity': 'CONDITIONAL'})
        self.assertFalse(eligibility(a, nonasserted)['eligible'])


if __name__ == '__main__':
    unittest.main()
