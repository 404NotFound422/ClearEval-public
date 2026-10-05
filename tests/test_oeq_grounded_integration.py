"""Normal OEQ CLI integration, actual guards and failure-aware resumption."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import OEQ_run_grading_new as runner
from evaluation_contract import CurrentDemandRegistry, json_hash, sha256_file
from oeq_scientific import build_context

CURRENT = 'dataset/Q+AR/src/question_final.json'
PROTOCOL = 'Chosen Method: MACS\nclearing 24 h\nNotes: ' + 'declared observation ' * 20


def teacher_payload(context):
    support = lambda v: dict(kind='EXPLICIT', raw_value=v, transform='IDENTITY', spans=[dict(quote=v)])
    fields = dict(phase='clearing', operation='clearing', duration_text='24 h')
    return dict(extraction=dict(schema_version='extraction-grounding-v2',
        branches=[dict(id='main', mode='SERIAL', sample_id='sample', spans=[])], labels=[], ri=[], limitations='',
        steps=[dict(id='S1',branch='main',quote='clearing 24 h',**fields,
                    field_support={k:support(v) for k,v in fields.items()},assertion=dict(polarity='AFFIRMED'))]),
        assessment=dict(schema_version='judgment-grounding-v2',limitations='',requirements=[
            dict(id=r['id'], status='UNRESOLVED', basis='MODEL_KNOWLEDGE', evidence_ids=[], quotes=[],
                 reason='No independent semantic verification provided.',evidence_checks=[])
            for r in context['requirements']]),objectives={})


class GroundedNormalTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.saved = (runner.QUESTION_FILE, runner.DEMAND_PROFILE, runner.DEMAND_FILE, runner.DEMAND_MANIFEST)
        runner.DEMAND_PROFILE='current-proposal'
        runner.configure_question_snapshot(CURRENT)
        self.question=runner._QUESTION_LIST[0]
        self.entry=dict(question_id=self.question['question_id'], specific_question=self.question['question'], model_response=PROTOCOL)
        self.context=runner._grounded_context(self.entry)
        self.teacher=SimpleNamespace(model_name='offline-grounded',_acall=AsyncMock(return_value={
            'content':json.dumps(teacher_payload(self.context)), 'metadata':{'technical_status':'VALID','finish_reason':'stop'}}))

    def tearDown(self):
        question,runner.DEMAND_PROFILE,runner.DEMAND_FILE,runner.DEMAND_MANIFEST=self.saved
        runner.configure_question_snapshot(question)

    async def test_explicit_grounded_cli_current_questions_and_resumes_without_call(self):
        protocol=PROTOCOL
        class SDK:
            calls=[]
            def __init__(self, **kwargs):pass
            def generate(self, **kwargs):
                SDK.calls.append(kwargs['model'])
                if kwargs['model']=='judge':
                    context=json.loads(kwargs['prompt'].split('\nCONTEXT_JSON\n',1)[1].split('\nSOURCE_RECORD_VIEW\n',1)[0].split('\nPROTOCOL\n',1)[0])
                    content=json.dumps(teacher_payload(context))
                else:content=protocol
                return dict(response=content,done=True,done_reason='stop',eval_count=50)
            def close(self):pass
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/'models.json'
            config.write_text(json.dumps({'models':[
                dict(name='candidate',type='Ollama',model_name='candidate',transport='sdk'),
                dict(name='judge',type='Ollama',model_name='judge',transport='sdk',format='json')]}),encoding='utf-8')
            responses,scores=Path(tmp)/'responses',Path(tmp)/'scores'
            args=['--assessment-mode','grounded','--model-config',str(config),'--models','candidate','--teacher','judge',
                  '--qids',str(self.question['question_id']),'--response-dir',str(responses),
                  '--score-dir',str(scores),'--eval-concurrency','1','--gen-concurrency','1']
            with patch.dict('sys.modules',{'ollama':SimpleNamespace(Client=SDK)}):
                self.assertEqual(await runner.main(args),0)
                self.assertEqual(await runner.main(args+['--eval-only']),0)
            record=json.loads((scores/'evaluation_results_candidate_1-shot.json').read_text(encoding='utf-8'))[0]['evaluation']
            summary=json.loads((scores/'evaluation_results_candidate_1-shot.json.diagnostics.json').read_text(encoding='utf-8'))
        self.assertEqual(SDK.calls,['candidate','judge'])
        self.assertEqual(record['scoring_status'],'GROUNDED_REQUIREMENT_ASSESSMENT')
        self.assertEqual(record['grounded_assessment']['text_completeness_decision']['status'],'UNDER_SPECIFIED')
        self.assertIn('requirement_results',record['grounded_assessment'])
        self.assertEqual(summary['technical_valid_count'],1)
        self.assertGreater(summary['expected_requirement_count'],2)
        self.assertIsNone(summary['formal_cce'])
        self.assertFalse(record['cce_eligible'])

    async def test_failed_raw_history_and_full_requirement_denominator_are_retained(self):
        raw=json.dumps(teacher_payload(self.context))
        failed={'content':raw,'metadata':{'technical_status':'FAILED','finish_reason':'length'}}
        self.teacher._acall.side_effect=[failed,{'content':raw,'metadata':{'technical_status':'VALID','finish_reason':'stop'}}]
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner,'OEQ_SCORE_DIR',tmp):
            path=await runner.evaluate_responses('candidate',[self.entry],self.teacher,{},'',assessment_mode='grounded')
            first=json.loads(Path(path+'.diagnostics.json').read_text(encoding='utf-8'))
            self.assertEqual(first['expected_requirement_count'],len(self.context['requirements']))
            self.assertEqual(first['full_input_requirement_decision_coverage'],0)
            self.assertEqual(first['not_assessed_requirement_count'],len(self.context['requirements']))
            await runner.evaluate_responses('candidate',[self.entry],self.teacher,{},'',assessment_mode='grounded')
            await runner.evaluate_responses('candidate',[self.entry],self.teacher,{},'',assessment_mode='grounded')
            saved=json.loads(Path(path).read_text(encoding='utf-8'))[0]
        self.assertEqual(self.teacher._acall.await_count,2)
        self.assertEqual(len(saved['previous_attempts']),1)
        self.assertEqual(saved['previous_attempts'][0]['evaluation']['teacher_generation']['raw_content'],raw)
        self.assertEqual(saved['previous_attempts'][0]['evaluation']['teacher_generation']['metadata']['finish_reason'],'length')
        self.assertEqual(saved['evaluation']['technical_status'],'VALID')

    async def test_self_rehashed_cached_judgment_is_recomputed_from_actual_teacher_raw(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner,'OEQ_SCORE_DIR',tmp):
            path=await runner.evaluate_responses('candidate',[self.entry],self.teacher,{},'',assessment_mode='grounded')
            records=json.loads(Path(path).read_text(encoding='utf-8'))
            assessment=records[0]['evaluation']['grounded_assessment']
            assessment['requirement_results'][0]['effective_status']='VIOLATED'
            records[0]['evaluation']['assessment_sha256']=json_hash(assessment)
            Path(path).write_text(json.dumps(records),encoding='utf-8')
            await runner.evaluate_responses('candidate',[self.entry],self.teacher,{},'',assessment_mode='grounded')
            after=json.loads(Path(path).read_text(encoding='utf-8'))[0]
        self.assertEqual(self.teacher._acall.await_count,2)
        self.assertEqual(after['evaluation']['grounded_assessment']['requirement_results'][0]['effective_status'],'SATISFIED')
        self.assertEqual(len(after['previous_attempts']),1)

    async def test_concurrent_interruption_preserves_pending_old_failure(self):
        import asyncio
        other=runner._QUESTION_LIST[1]
        entries=[self.entry,dict(question_id=other['question_id'],specific_question=other['question'],model_response=PROTOCOL)]
        async def failing(prompt):
            return {'content':'unfinished','metadata':{'technical_status':'FAILED','finish_reason':'length'}}
        self.teacher._acall.side_effect=failing
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner,'OEQ_SCORE_DIR',tmp):
            path=await runner.evaluate_responses('candidate',entries,self.teacher,{},'',assessment_mode='grounded',eval_concurrency=2)
            old=json.loads(Path(path).read_text(encoding='utf-8'))
            old_other=next(row for row in old if row['question_id']==other['question_id'])
            async def interrupted(prompt):
                context=json.loads(prompt.split('\nCONTEXT_JSON\n',1)[1].split('\nSOURCE_RECORD_VIEW\n',1)[0].split('\nPROTOCOL\n',1)[0])
                if context['question_meta']['question_id']==other['question_id']:
                    await asyncio.sleep(.05)
                    raise asyncio.CancelledError()
                return {'content':json.dumps(teacher_payload(context)), 'metadata':{'technical_status':'VALID','finish_reason':'stop'}}
            self.teacher._acall.side_effect=interrupted
            with self.assertRaises(asyncio.CancelledError):
                await runner.evaluate_responses('candidate',entries,self.teacher,{},'',assessment_mode='grounded',eval_concurrency=2)
            after=json.loads(Path(path).read_text(encoding='utf-8'))
            self.assertEqual(next(row for row in after if row['question_id']==other['question_id']),old_other)
            self.assertEqual(len(after),2)

    async def test_failure_sidecar_preserves_multiple_literal_errors_and_locations(self):
        proposal=teacher_payload(self.context)
        fields=proposal['extraction']['steps'][0]['field_support']
        proposal['extraction']['steps'][0]['operation']='summary operation'
        fields['operation'].update(raw_value='summary operation',spans=[{'quote':'declared observation'}])
        proposal['extraction']['steps'][0]['duration_text']='48 h'
        fields['duration_text'].update(raw_value='48 h')
        raw=json.dumps(proposal)
        self.teacher._acall.return_value={'content':raw,'metadata':{'technical_status':'VALID','finish_reason':'stop'}}
        result=await runner.evaluate_grounded_response(self.teacher,self.entry,self.context)
        self.assertEqual(result['technical_status'],'FAILED')
        self.assertEqual(result['failure_stage'],'GROUNDING_VALIDATION')
        self.assertEqual(len(result['grounding_diagnostics']['hard_errors']),2)
        self.assertEqual(result['grounding_diagnostics']['ambiguous_locations'],1)
        self.assertFalse(result['grounding_diagnostics']['certification'])
        self.assertEqual(result['teacher_proposal'],proposal)
        self.assertIsNone(result['official_scores'])
        self.assertNotIn('grounded_assessment',result)

    async def test_context_mismatch_is_rejected_before_teacher_call(self):
        wrong={str(self.entry['question_id']):dict(question_sha256='0'*64,protocol_sha256=self.context['protocol_sha256'])}
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner,'OEQ_SCORE_DIR',tmp),self.assertRaises(ValueError):
            await runner.evaluate_responses('candidate',[self.entry],self.teacher,{},'',assessment_mode='grounded',task_contexts=wrong)
        self.assertEqual(self.teacher._acall.await_count,0)

    def test_current_profile_preserves_original_vectors_and_scientific_unknowns(self):
        path='dataset/Q+AR/src/demand_vectors_all.json'
        before=sha256_file(path)
        registry=CurrentDemandRegistry(CURRENT)
        self.assertEqual(len(registry.questions),253)
        self.assertIsNone(registry.provenance['scientific_approval'])
        self.assertEqual(registry.provenance['numeric_scale_status'],'UNCALIBRATED_PROJECTION_FOR_REVIEW')
        self.assertEqual(sha256_file(path),before)
        with self.assertRaises(ValueError):registry.get(self.entry['question_id'],'old text')

    def test_missing_teacher_raw_is_not_a_completed_cached_scientific_record(self):
        from oeq_scientific import VERSION
        assessment={'schema_version':VERSION,'technical_status':'VALID','requirement_results':[]}
        ev=dict(technical_status='VALID',scoring_status='GROUNDED_REQUIREMENT_ASSESSMENT',
                cce_eligible=False,official_scores=None,grounded_assessment=assessment,assessment_sha256=json_hash(assessment))
        self.assertFalse(runner._grounded_complete(ev))

if __name__=='__main__':unittest.main()