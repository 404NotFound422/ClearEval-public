"""Small attribution regressions; no benchmark-wide scoring or model calls."""
import unittest
from unittest.mock import patch

import cleareval_complete_scoring as complete
from cleareval_scoring import scoring_v5,scoring_v6,adjudication
from test_claim_integration import example

GOOD = 'Incubate in full CUBIC-R1 (25% w/w urea, 25% w/w Quadrol, 15% w/w Triton X-100).'
BAD = GOOD.replace('25% w/w urea', '30% w/w urea')
BARE = 'Incubate in full CUBIC-R1.'


def case_for(texts):
    case = example()
    case['candidate_steps'] = [dict(id=f'C{i+1}', text=t, heading='Tissue Optical Clearing', occurrences=1)
                               for i, t in enumerate(texts)]
    case['reference_steps'] = [dict(id=f'R{i+1}', text=BARE, heading='Tissue Optical Clearing', occurrences=1)
                               for i in range(len(texts))]
    case['answer'] = '\n'.join(texts)
    return case


def pair_states(packet):
    return {p['candidate']: p['correctness_status'] for p in packet['written']['pairs']}


def main_correctness(case, packet):
    old = {k: {'value': v} for k, v in [('co_order', 3), ('co_method', 2), ('co_param', 2), ('co_chem', 1)]}
    return complete.correctness(case, packet, old, {'order_resolutions': {}})


class ClaimOwnershipTests(unittest.TestCase):
    def test_each_inline_definition_only_checks_its_own_use(self):
        for texts, expected in [([GOOD, BAD], ['PASS', 'FAIL']), ([BAD, GOOD], ['FAIL', 'PASS'])]:
            with self.subTest(texts=texts):
                case = case_for(texts)
                packet = scoring_v6.score_branch(case)
                self.assertEqual(list(pair_states(packet).values()), expected)
                for mode in ['written', 'occurrence']:
                    self.assertEqual(packet[mode]['metrics']['confirmed_correct_credit'], 1)
                    self.assertEqual(packet[mode]['metrics']['correctness_Bio_SR'], 0.5)
                findings = main_correctness(case, packet)['co_param']['findings']
                self.assertEqual([f['candidate'] for f in findings], [f'C{expected.index("FAIL")+1}'])

    def test_future_inline_definition_does_not_change_earlier_use(self):
        packet = scoring_v6.score_branch(case_for([BARE, BAD]))
        self.assertEqual(pair_states(packet), {'C1': 'PASS', 'C2': 'FAIL'})

    def test_later_reuse_inherits_preceding_definition(self):
        packet = scoring_v6.score_branch(case_for([BAD, BARE]))
        self.assertEqual(pair_states(packet), {'C1': 'FAIL', 'C2': 'FAIL'})
        self.assertEqual(packet['operation_claim_audit'][1]['claims'][0]['definition_candidate'], 'C1')

    def test_recipe_appendix_is_still_bound_to_bare_use(self):
        case = case_for([BARE])
        case['candidate_steps'].append(dict(id='P1', text=BAD.replace('Incubate in full', 'Prepare'),
                                            heading='Reagent preparation', occurrences=1))
        case['answer'] = '\n'.join(s['text'] for s in case['candidate_steps'])
        packet = scoring_v6.score_branch(case)
        self.assertEqual(pair_states(packet), {'C1': 'FAIL'})
        self.assertEqual(packet['written']['metrics']['N_C'], 1)

    def test_inline_recipe_takes_priority_over_appendix(self):
        case = case_for([GOOD])
        case['candidate_steps'].append(dict(id='P1', text=BAD.replace('Incubate in full', 'Prepare'),
                                            heading='Reagent preparation', occurrences=1))
        case['answer'] = '\n'.join(s['text'] for s in case['candidate_steps'])
        self.assertEqual(pair_states(scoring_v6.score_branch(case)), {'C1': 'PASS'})

    def test_negated_additive_is_not_an_added_ingredient(self):
        for note in ['do not add 5% DMSO', 'without 5% DMSO', '不要添加 5% DMSO']:
            with self.subTest(note=note):
                case = case_for([GOOD.replace(').', '; ' + note + ').')])
                packet = scoring_v6.score_branch(case)
                self.assertEqual(pair_states(packet), {'C1': 'PASS'})
                self.assertEqual(main_correctness(case, packet)['co_method']['value'], 2)

    def test_positive_addition_after_negative_note_still_fails(self):
        text = GOOD.replace(').', '; do not add 5% DMSO; add 1% DMSO).')
        self.assertEqual(pair_states(scoring_v6.score_branch(case_for([text]))), {'C1': 'FAIL'})

    def test_same_line_wash_does_not_redefine_stock(self):
        case = case_for([GOOD, 'Wash in 5% DMSO.'])
        case['reference_steps'][1]['text'] = 'Wash in 5% DMSO.'
        case['answer'] = '; '.join(s['text'] for s in case['candidate_steps'])
        packet = scoring_v6.score_branch(case)
        self.assertEqual(pair_states(packet), {'C1': 'PASS', 'C2': 'PASS'})
        out = main_correctness(case, packet)
        self.assertFalse(out['co_method'].get('findings'))
        self.assertFalse(out['co_param'].get('findings'))

    def test_missing_recipe_unit_remains_unresolved(self):
        case = case_for([GOOD.replace('25% w/w urea', '25% urea')])
        packet = scoring_v6.score_branch(case)
        self.assertEqual(pair_states(packet), {'C1': 'REVIEW'})
        self.assertEqual(main_correctness(case, packet)['co_param']['status'], 'PROVISIONAL')

    def test_conflicting_recipe_appendices_do_not_select_arbitrarily(self):
        case = case_for([BARE])
        for i, text in enumerate([GOOD, BAD]):
            case['candidate_steps'].append(dict(id=f'P{i+1}', text=text.replace('Incubate in full', 'Prepare'),
                                                heading='Reagent preparation', occurrences=1))
        case['answer'] = '\n'.join(s['text'] for s in case['candidate_steps'])
        packet = scoring_v6.score_branch(case)
        self.assertEqual(pair_states(packet), {'C1': 'REVIEW'})
        self.assertEqual(packet['operation_claim_audit'][0]['reason'], 'AMBIGUOUS_STOCK_DEFINITION')

    def test_prohibited_required_component_does_not_count_as_present(self):
        text = GOOD.replace('25% w/w urea', 'do not add 25% w/w urea')
        packet = scoring_v6.score_branch(case_for([text]))
        self.assertEqual(pair_states(packet), {'C1': 'REVIEW'})

    def test_old_candidate_cache_is_not_labeled_as_new_result(self):
        version = complete.VERSION
        try:
            with patch.object(complete, 'verified_packets') as recompute:
                with self.assertRaisesRegex(AssertionError, 'different scoring version'):
                    complete.main(['--cached-checks', '--verified',
                                   str(complete.ROOT/'dataset/benchmark185/2026-11-05/verified_checks.json.gz')])
                recompute.assert_not_called()
        finally:
            complete.VERSION = version

    def test_patch_reuses_alignment_without_mutating_cached_packet(self):
        case = case_for([GOOD, BAD])
        cached = adjudication.apply(scoring_v5.score_branch(case), case, [])
        original_states = pair_states(cached)
        with patch.object(scoring_v5, 'score_branch', side_effect=AssertionError('Alignment was rerun')):
            packet = scoring_v6.apply_to_cached_packet(case, cached)
        self.assertEqual(pair_states(packet), {'C1': 'PASS', 'C2': 'FAIL'})
        self.assertEqual(pair_states(cached), original_states)
        for mode in ['written', 'occurrence']:
            before = [(p['candidate'], p['reference'], p['count']) for p in cached[mode]['pairs']]
            after = [(p['candidate'], p['reference'], p['count']) for p in packet[mode]['pairs']]
            self.assertEqual(before, after)

    def test_explicit_review_remains_local_and_authoritative(self):
        case = case_for([GOOD, BAD])
        decision = dict(id=case['id'], reference_links=[{'branch': case['branch']}],
                        candidate_ids=['C2'], field='declared_recipe:cubic_r1', state='PASS',
                        review_id='constructed-review', group_id='recipe_ratio')
        packet = scoring_v6.score_branch(case, [decision])
        self.assertEqual(pair_states(packet), {'C1': 'PASS', 'C2': 'PASS'})
        self.assertFalse(packet['independent_recipe_findings'])


if __name__ == '__main__':
    unittest.main()
