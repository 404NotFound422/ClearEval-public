"""Published recommendation scope and normal-flow failure persistence."""

from copy import deepcopy

import json

from pathlib import Path

import tempfile

from types import SimpleNamespace

import unittest

from unittest.mock import AsyncMock, patch



import OEQ_run_grading_new as runner

from evaluation_contract import json_hash

from oeq_scientific import ROOT, _cards, build_context

from experiments.construct_validity.source_conditions import diagnose, load_rules



HEADER = 'Chosen Method: CUBIC\n'

STORAGE = 'Store the sample in CUBIC-R+(M) (Temperature: 4 C, Time: 7 days)'

METHODS = ['CUBIC', 'FDISCO', 'MACS', 'SeeDB2']





def teacher_payload(context):

    support = lambda value: dict(kind='EXPLICIT', raw_value=value, transform='IDENTITY', spans=[dict(quote=value)])

    fields = dict(phase='clearing', operation='clearing', duration_text='24 h')

    return dict(extraction=dict(schema_version='extraction-grounding-v2',

        branches=[dict(id='main', mode='SERIAL', sample_id='sample', spans=[])], labels=[], ri=[], limitations='',

        steps=[dict(id='S1', branch='main', quote='clearing 24 h', **fields,

            field_support={k:support(v) for k,v in fields.items()}, assertion=dict(polarity='AFFIRMED'))]),

        assessment=dict(schema_version='judgment-grounding-v2', limitations='', requirements=[

            dict(id=r['id'], status='UNRESOLVED', basis='MODEL_KNOWLEDGE', evidence_ids=[], quotes=[],

                 reason='No independent scientific verification.', evidence_checks=[])

            for r in context['requirements']]), objectives={})





class SourceRecommendationTests(unittest.TestCase):

    @classmethod

    def setUpClass(cls):

        cls.cards = _cards(ROOT)

        cls.rules = load_rules(ROOT)



    def run_case(self, protocol, cards=None, rules=None):

        return diagnose(protocol, self.cards if cards is None else cards,

                        self.rules if rules is None else rules, method_keys=METHODS)



    def test_explicit_storage_warning_has_original_source_binding_and_no_science_label(self):

        text = HEADER + STORAGE + '\nEquilibrate for imaging at room temperature.'

        result = self.run_case(text)

        self.assertEqual(result['potential_conflict_count'], 1)

        finding = result['findings'][0]

        self.assertEqual(finding['status'], 'POTENTIAL_AUTHOR_GUIDANCE_CONFLICT')

        self.assertEqual(text[finding['temperature_span']['start']:finding['temperature_span']['end']], '4 C')

        self.assertFalse(finding['changes_requirement_states'])

        self.assertIsNone(result['independent_scientific_truth'])

        self.assertIn('NON_GEL_SOURCE_SCOPE_NOT_FULLY_ESTABLISHED', finding['source_scope_guards'])

        self.assertTrue(finding['source_proof']['guidance_span']['quote'].endswith('crystallize.'))

        for suffix in [', avoid light.', ', avoid photobleaching.']:

            self.assertEqual(self.run_case(HEADER + STORAGE + suffix)['potential_conflict_count'], 1)

        self.assertEqual(self.run_case(HEADER + 'Avoid light:\n' + STORAGE)['potential_conflict_count'], 1)



    def test_pbs_pause_agarose_cooling_and_later_4c_do_not_borrow_storage_temperature(self):

        cases = [

            HEADER + 'Store the sample in PBS (Temperature: 4 C)\nCUBIC-R+ matching at room temperature.',

            HEADER + 'Gel the CUBIC-R+ sample in agarose (Temperature: 4 C)',

            HEADER + 'Store the sample in CUBIC-R+ (Temperature: 20 C)\nWash in PBS (Temperature: 4 C)',

            HEADER + 'Fixation uses 4% PFA.\nStore the sample in CUBIC-R+ (Temperature: 20 C)',

        ]

        for text in cases:

            with self.subTest(text=text):

                self.assertEqual(self.run_case(text)['potential_conflict_count'], 0)

        result = self.run_case(cases[2])

        self.assertEqual(result['findings'][0]['status'], 'CONDITION_NOT_MATCHED')



    def test_conditions_negation_and_other_method_scopes_require_review(self):

        cases = [

            HEADER + 'If required:\n' + STORAGE,

            HEADER + '### If required\n' + STORAGE,

            HEADER + 'Only if required.\n' + STORAGE,

            'If required:\n' + HEADER + STORAGE,

            HEADER + '\u6309\u9700\u4fdd\u5b58\uff1a\n' + STORAGE,

            HEADER + '\u5982\u9700\u6682\u5b58\uff1a\n' + STORAGE,

            HEADER + 'FDISCO:\n' + STORAGE,

            HEADER + 'Branch B (FDISCO):\n' + STORAGE,

            HEADER + 'Do not perform the following:\n' + STORAGE,

            HEADER + 'Alternative FDISCO route:\n' + STORAGE,

            HEADER + 'Reagent stock handling:\nStore reagent stock in CUBIC-R+ (Temperature: 4 C)',

            HEADER + STORAGE.replace('Store', 'Do not store'),

            HEADER + 'If required, ' + STORAGE,

            'Chosen Method: FDISCO\n' + STORAGE,

        ]

        for text in cases:

            with self.subTest(text=text):

                result = self.run_case(text)

                self.assertEqual(result['potential_conflict_count'], 0)

                self.assertGreater(result['review_required_count'], 0)



    def test_post_metadata_restrictions_and_conflicting_temperatures_require_review(self):

        cases = [

            HEADER + STORAGE + ', if required',

            HEADER + STORAGE + '; do not perform this operation',

            HEADER + STORAGE + ', not performed.',

            HEADER + STORAGE + ', rejected.',

            HEADER + STORAGE + ', \u672a\u6267\u884c\u3002',

            HEADER + STORAGE.replace(' (Temperature', ' at 20 C (Temperature'),

            HEADER + STORAGE.replace(' (Temperature', ' at room temperature (Temperature') + '; fixation only',

        ]

        for text in cases:

            with self.subTest(text=text):

                result = self.run_case(text)

                self.assertEqual(result['potential_conflict_count'], 0)

                self.assertGreater(result['review_required_count'], 0)



    def test_missing_range_multiple_media_and_unproven_sample_do_not_certify_warning(self):

        cases = [

            HEADER + 'Store the sample in CUBIC-R+.',

            HEADER + STORAGE.replace('4 C', '4-20 C'),

            HEADER + 'Store the sample in CUBIC-R+ or CUBIC-R+(M) (Temperature: 4 C)',

            HEADER + 'Store reagent stock in CUBIC-R+ (Temperature: 4 C)',

            HEADER + 'Store the bottle in CUBIC-R+ (Temperature: 4 C)',

        ]

        for text in cases:

            with self.subTest(text=text):

                result = self.run_case(text)

                self.assertEqual(result['potential_conflict_count'], 0)

                self.assertGreater(result['review_required_count'], 0)



    def test_missing_source_abstains_and_tampered_source_version_span_or_policy_rejected(self):

        text = HEADER + STORAGE

        missing = self.run_case(text, cards=[])

        self.assertEqual(missing['rule_audits'][0]['status'], 'SOURCE_NOT_SELECTED')

        self.assertEqual(missing['potential_conflict_count'], 0)

        for field, value in [('source_sha256', '0'*64), ('source_version', 'other-version'),

                             ('decision_policy', 'MANDATORY_FAILURE'), ('avoid_temperature_C', 5)]:

            rules = deepcopy(self.rules)

            rules['rules'][0][field] = value

            with self.subTest(field=field), self.assertRaises(ValueError):

                self.run_case(text, rules=rules)

        rules = deepcopy(self.rules)

        rules['rules'][0]['source_guidance_span']['end'] -= 1

        with self.assertRaises(ValueError):

            self.run_case(text, rules=rules)

        cards = deepcopy(self.cards)

        card = next(c for c in cards if c['id'] == self.rules['rules'][0]['source_id'])

        card['source_document']['text'] += 'changed'

        with self.assertRaises(ValueError):

            self.run_case(text, cards=cards)





class SourceRecommendationNormalFlowTests(unittest.IsolatedAsyncioTestCase):

    def setUp(self):

        self.saved = (runner.QUESTION_FILE, runner.DEMAND_PROFILE, runner.DEMAND_FILE, runner.DEMAND_MANIFEST)

        runner.DEMAND_PROFILE = 'current-proposal'

        runner.configure_question_snapshot('dataset/Q+AR/src/question_final.json')

        question = runner._QUESTION_LIST[0]

        self.protocol = HEADER + STORAGE + '\nclearing 24 h'

        self.entry = dict(question_id=question['question_id'], specific_question=question['question'], model_response=self.protocol)

        self.context = runner._grounded_context(self.entry)

        self.teacher = SimpleNamespace(model_name='offline-source-scope', _acall=AsyncMock())



    def tearDown(self):

        question, runner.DEMAND_PROFILE, runner.DEMAND_FILE, runner.DEMAND_MANIFEST = self.saved

        runner.configure_question_snapshot(question)



    async def test_teacher_generation_and_json_failure_persist_advisory_with_failed_denominator(self):

        cases = [dict(content='unfinished', metadata=dict(technical_status='FAILED', finish_reason='length')),

                 dict(content='{broken', metadata=dict(technical_status='VALID', finish_reason='stop'))]

        for index, returned in enumerate(cases):

            with self.subTest(index=index), tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'OEQ_SCORE_DIR', tmp):

                self.teacher._acall.return_value = returned

                path = await runner.evaluate_responses('candidate', [self.entry], self.teacher, {}, '', assessment_mode='grounded')

                record = json.loads(Path(path).read_text(encoding='utf-8'))[0]['evaluation']

                summary = json.loads(Path(path+'.diagnostics.json').read_text(encoding='utf-8'))

            self.assertEqual(record['technical_status'], 'FAILED')

            diagnostics = record['source_condition_diagnostics']

            self.assertEqual(diagnostics['potential_conflict_count'], 1)

            self.assertEqual(record['source_condition_diagnostics_sha256'], json_hash(diagnostics))

            self.assertEqual(summary['source_guidance_potential_conflict_count'], 1)

            self.assertEqual(summary['technical_failure_count'], 1)

            self.assertEqual(summary['full_input_requirement_decision_coverage'], 0)

            self.assertIsNone(summary['independent_scientific_accuracy'])



    async def test_seedb2_local_risk_survives_failed_teacher_and_summary_counts_role(self):
        entry = dict(self.entry, model_response='Chosen Method: SeeDB2\nDilute SeeDB2S with PBS.\nclearing 24 h')
        self.teacher._acall.return_value = dict(content='unfinished',
            metadata=dict(technical_status='FAILED', finish_reason='length'))
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'OEQ_SCORE_DIR', tmp):
            path = await runner.evaluate_responses('candidate', [entry], self.teacher, {}, '', assessment_mode='grounded')
            evaluation = json.loads(Path(path).read_text(encoding='utf-8'))[0]['evaluation']
            summary = json.loads(Path(path+'.diagnostics.json').read_text(encoding='utf-8'))
        self.assertEqual(evaluation['technical_status'], 'FAILED')
        self.assertEqual(evaluation['source_condition_diagnostics']['local_risk_count'], 1)
        self.assertEqual(summary['source_local_potential_risk_count'], 1)
        self.assertEqual(summary['source_author_recipe_nonconformance_count'], 0)
        self.assertEqual(summary['source_guidance_potential_conflict_count'], 0)
        self.assertEqual(summary['technical_failure_count'], 1)
        self.assertEqual(summary['full_input_requirement_decision_coverage'], 0)
        self.assertIsNone(summary['independent_scientific_accuracy'])

    async def test_cached_self_rehashed_advisory_is_recomputed_and_previous_attempt_kept(self):

        self.teacher._acall.return_value = dict(content=json.dumps(teacher_payload(self.context)),

            metadata=dict(technical_status='VALID', finish_reason='stop'))

        with tempfile.TemporaryDirectory() as tmp, patch.object(runner, 'OEQ_SCORE_DIR', tmp):

            path = await runner.evaluate_responses('candidate', [self.entry], self.teacher, {}, '', assessment_mode='grounded')

            rows = json.loads(Path(path).read_text(encoding='utf-8'))

            evaluation = rows[0]['evaluation']

            diagnostics = evaluation['source_condition_diagnostics']

            diagnostics['potential_conflict_count'] = 0

            diagnostics['findings'][0]['status'] = 'CONDITION_NOT_MATCHED'

            evaluation['source_condition_diagnostics_sha256'] = json_hash(diagnostics)

            evaluation['grounded_assessment']['source_condition_diagnostics'] = deepcopy(diagnostics)

            evaluation['assessment_sha256'] = json_hash(evaluation['grounded_assessment'])

            Path(path).write_text(json.dumps(rows), encoding='utf-8')

            await runner.evaluate_responses('candidate', [self.entry], self.teacher, {}, '', assessment_mode='grounded')

            await runner.evaluate_responses('candidate', [self.entry], self.teacher, {}, '', assessment_mode='grounded')

            after = json.loads(Path(path).read_text(encoding='utf-8'))[0]

        self.assertEqual(self.teacher._acall.await_count, 2)

        self.assertEqual(after['evaluation']['source_condition_diagnostics']['potential_conflict_count'], 1)

        self.assertEqual(len(after['previous_attempts']), 1)

        self.assertIsNone(after['evaluation']['official_scores'])





if __name__ == '__main__':

    unittest.main()

