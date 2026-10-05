import unittest
from copy import deepcopy
from pathlib import Path
from oeq_scientific import build_context, apply_assessment, compare_assessments
from experiments.construct_validity.fidelity import text_hash


def req(rid='R',kind='TEXT',rule=None,**extra):
    r=dict(id=rid,kind=kind,text='Literal contract '+rid,necessary=True,evidence_ids=[],**extra)
    if rule is not None:r['literal_rule']=rule
    return r


def extraction(text='clearing 24 h'):
    support=lambda value: dict(kind='EXPLICIT',raw_value=value,transform='IDENTITY',spans=[dict(quote=value)])
    return dict(schema_version='extraction-grounding-v2',branches=[dict(id='main',mode='SERIAL',sample_id='sample',spans=[])],labels=[],ri=[],limitations='',
        steps=[dict(id='S1',branch='main',phase='clearing',operation='clearing',duration_text='24 h',quote=text,
                    field_support={k:support(v) for k,v in dict(phase='clearing',operation='clearing',duration_text='24 h').items()},assertion=dict(polarity='AFFIRMED'))])


def payload(context,text='clearing 24 h'):
    return dict(extraction=extraction(text),assessment=dict(schema_version='judgment-grounding-v2',limitations='',requirements=[
        dict(id=r['id'],status='SATISFIED',basis='PROTOCOL_TEXT',evidence_ids=[],quotes=[text],reason='Original text declaration',evidence_checks=[])
        for r in context['requirements']]),objectives={})



def payload_with_ri(c,ext):
    raw=payload(c,'clearing 24 h')
    raw['extraction']=deepcopy(ext)
    for record in raw['assessment']['requirements']:record['quotes']=['MACS RI = 1.53']
    return raw


def literal_case():
    source='MACS RI = 1.51'
    text='MACS RI = 1.53; clearing 24 h'
    def spans(body,value):
        start=body.index(value);return dict(start=start,end=start+len(value),quote=value)
    def binding(body,value):
        return dict(span=spans(body,body.split(';')[0]),entity_span=spans(body,'MACS'),dimension_span=spans(body,'RI'),value_span=spans(body,value),polarity='AFFIRMED')
    sb=binding(source,'1.51');sb.update(source_id='C',passage_id='P')
    pb=binding(text,'1.53');pb.update(collection='ri',branch='main')
    card=dict(id='C',schema_version='source-grounding-v2',identity=dict(url='https://example.org/source',version='v1',publication_status='CURRENT'),
              source_document=dict(text=source,sha256=text_hash(source),url='https://example.org/source',version='v1'),
              passages=[dict(id='P',start=0,end=len(source),quote=source,sha256=text_hash(source))],applicability={})
    rule=dict(type='SOURCE_LITERAL_EQUALITY',field='value_text',entity_field='solution',entity='MACS',dimension='RI',polarity='AFFIRMED',source_binding=sb,protocol_binding=pb)
    c=build_context({},text,study_context={'requirements':[req(rule=rule)],'cards':[card]})
    ext=extraction(text)
    ext['ri']=[dict(branch='main',solution='MACS',value_text='1.53',quote='MACS RI = 1.53',assertion=dict(polarity='AFFIRMED'),field_support={
        f:dict(kind='EXPLICIT',raw_value=v,transform='IDENTITY',spans=[spans(text,v)]) for f,v in [('solution','MACS'),('value_text','1.53')]})]
    return c,payload_with_ri(c,ext),text
class ScientificBridgeTests(unittest.TestCase):
    def test_normal_scope_has_partial_local_decision(self):
        c=build_context({'question':'Already fixed and labels QC passed. Only clearing.'},'MACS: clearing 24 h',workspace=Path('not_existing'))
        raw=payload(c,'MACS: clearing 24 h')
        raw['method_declarations']=[dict(name='MACS',branch='main',span={'quote':'MACS'})]
        result=apply_assessment(raw,c,'MACS: clearing 24 h')
        self.assertEqual(result['text_completeness_decision']['status'],'SATISFIED')
        self.assertEqual(result['scientific_applicability_decision']['status'],'UNRESOLVED')
        self.assertFalse(result['extraction_fidelity']['completeness_certified'])
        self.assertIsNone(result['experimental_success_claim'])
        self.assertEqual(c['origin'],'AUTO_PROVISIONAL_NOT_DOMAIN_REVIEWED')
        self.assertNotIn('PNAd',c['prompt'])

    def test_fidelity_mismatch_and_duplicate_quote_rejected(self):
        c=build_context({},'clearing 24 h',study_context={'requirements':[req(rule={'type':'LITERAL_REQUIRED','text':'clearing'})]})
        raw=payload(c)
        raw['extraction']['steps'][0]['duration_text']='48 h'
        with self.assertRaises(ValueError):apply_assessment(raw,c,'clearing 24 h')
        c=build_context({},'clearing 24 h; clearing 24 h',study_context={'requirements':[req()]})
        result=apply_assessment(payload(c),c,'clearing 24 h; clearing 24 h')
        self.assertEqual(result['technical_status'],'VALID')
        self.assertFalse(result['extraction_fidelity']['scoring_eligible'])

    def test_omission_keeps_bidirectional_partial(self):
        text='clearing 24 h; storage 12 h'
        inventory=[dict(collection='steps',field='duration_text',span=dict(start=9,end=13,quote='24 h')),
                   dict(collection='steps',field='duration_text',span=dict(start=23,end=27,quote='12 h'))]
        c=build_context({},text,study_context={'requirements':[req(rule={'type':'LITERAL_REQUIRED','text':'clearing'})],'field_inventory':inventory})
        result=apply_assessment(payload(c,text),c,text)
        self.assertEqual(result['extraction_fidelity']['inventory_recall'],.5)
        self.assertEqual(len(result['extraction_fidelity']['missing_fields']),1)
        self.assertFalse(result['extraction_fidelity']['completeness_certified'])

    def test_hard_requirement_not_bypassed_by_requested_formula(self):
        rs=[req('H',rule={'type':'LITERAL_REQUIRED','text':'mounting'}),req('A',rule={'type':'LITERAL_REQUIRED','text':'clearing'},scope='ROUTE',route_id='A')]
        c=build_context({},'clearing 24 h',study_context={'requirements':rs,'formula':{'any':['A']}})
        result=apply_assessment(payload(c),c,'clearing 24 h')
        self.assertEqual(result['overall'],'UNDER_SPECIFIED')
        self.assertEqual(result['route_results'][0]['status'],'UNRESOLVED')

    def test_frozen_source_literal_conflict_without_science_claim(self):
        c,raw,text=literal_case()
        result=apply_assessment(raw,c,text)
        self.assertEqual(result['source_consistency_decision']['status'],'VIOLATED')
        self.assertEqual(result['scientific_applicability_decision']['status'],'UNRESOLVED')
        self.assertIsNone(result['scientific_gold'])
    def test_semantically_identical_question_key_order_has_identical_prompt_bytes(self):
        text='MACS: clearing 24 h'
        first={'question_id':9,'question':'Already fixed. Clearing only.',
               'nested':{'one':1,'two':2}}
        second={'nested':{'two':2,'one':1},'question':first['question'],'question_id':9}
        a=build_context(first,text,workspace=Path('not_existing'))
        b=build_context(second,text,workspace=Path('not_existing'))
        self.assertEqual(a['context_sha256'],b['context_sha256'])
        self.assertEqual(a['prompt'],b['prompt'])
        self.assertEqual(a['prompt_sha256'],b['prompt_sha256'])

    def test_context_mutation_refused(self):
        c=build_context({},'clearing 24 h',study_context={'requirements':[req()]})
        raw=payload(c)
        c['requirements'][0]['necessary']=False
        with self.assertRaises(ValueError):apply_assessment(raw,c,'clearing 24 h')

    def test_objectives_use_existing_scope_guard(self):
        rs=[req(rule={'type':'LITERAL_REQUIRED','text':'clearing'})]
        def evaluate(text,value,scope):
            c=build_context({'id':1},text,study_context={'requirements':rs,'scope':{'sample':'same'},'verified_objectives':{'time':dict(min=value,max=value,direction='min',unit='h',measurement_scope=scope)}})
            return apply_assessment(payload(c,text),c,text)
        a=evaluate('clearing 24 h',24,'clearing_only')
        b=evaluate('clearing 24 h. extra',30,'clearing_only')
        self.assertEqual(compare_assessments(a,b)['relationship'],'A_DOMINATES')
        b=evaluate('clearing 24 h. extra',30,'including_storage')
        self.assertEqual(compare_assessments(a,b)['relationship'],'NOT_COMPARABLE')

    def test_cross_record_label_does_not_erase_independently_grounded_step_or_name(self):
        text='MACS: clearing 24 h\nTarget A uses DiI.\nTarget B uses FITC.'
        context=build_context({},text,workspace=Path('not_existing'))
        raw=payload(context,text)
        raw['method_declarations']=[dict(name='MACS',branch='main',span={'quote':'MACS'})]
        support=lambda value: dict(kind='EXPLICIT',raw_value=value,transform='IDENTITY',spans=[{'quote':value}])
        missing=dict(kind='MISSING',raw_value=None,spans=[])
        raw['extraction']['labels']=[dict(id='L',branch='main',target='Target B',probe='DiI',
            fluorophore=None,channel=None,quote='Target B uses FITC.',assertion={'polarity':'AFFIRMED'},
            field_support={'target':support('Target B'),'probe':support('DiI'),
                           'fluorophore':deepcopy(missing),'channel':deepcopy(missing)})]
        result=apply_assessment(raw,context,text)
        self.assertEqual(result['technical_status'],'VALID')
        self.assertFalse(result['extraction_fidelity']['scoring_eligible'])
        label=next(f for f in result['extraction_fidelity']['facts'] if f['collection']=='labels')
        self.assertEqual(label['fields']['probe']['status'],'REVIEW_REQUIRED')
        observed={r['id']:r['effective_status'] for r in result['requirement_results']}
        self.assertEqual(observed['DECLARED_STEPS'],'SATISFIED')
        self.assertEqual(observed['SINGLE_METHOD_IDENTITY'],'SATISFIED')
        self.assertEqual(observed['DECLARED_APPLICABILITY'],'UNRESOLVED')
        self.assertIsNone(result['experimental_success_claim'])

    def test_conditional_repeat_operation_remains_undecided(self):
        text='If ready, repeat fixation'
        context=build_context({},text,study_context={'requirements':[req(rule={'type':'NO_REPEAT_FIXATION'})]})
        raw=payload(context,text)
        row=raw['extraction']['steps'][0]
        row.update(phase=None,operation='repeat fixation',duration_text=None,assertion={'polarity':'CONDITIONAL'})
        row['field_support']={k:(dict(kind='MISSING',raw_value=None,spans=[]) if v is None else
            dict(kind='EXPLICIT',raw_value=v,transform='IDENTITY',spans=[{'quote':v}]))
            for k,v in [('phase',None),('operation','repeat fixation'),('duration_text',None)]}
        result=apply_assessment(raw,context,text)
        self.assertEqual(result['requirement_results'][0]['effective_status'],'UNRESOLVED')
        self.assertEqual(result['requirement_results'][0]['verification']['conditional_step_ids'],['S1'])

    def test_negative_conditional_or_rejected_method_mentions_do_not_prove_selection(self):
        for text in ['Do not use MACS.','If ready, use MACS.','Rejected Method: MACS']:
            context=build_context({},text,study_context={'requirements':[req(rule={'type':'METHOD_IDENTITY_SINGLE'})]})
            raw=payload(context,text)
            raw['extraction']['steps']=[]
            raw['method_declarations']=[dict(name='MACS',branch='main',span={'quote':'MACS'})]
            result=apply_assessment(raw,context,text)
            self.assertEqual(result['method_identity']['status'],'UNRESOLVED')
            self.assertNotEqual(result['requirement_results'][0]['effective_status'],'SATISFIED')

    def test_selected_role_cannot_be_borrowed_from_another_same_name_occurrence(self):
        text='Rejected method: MACS; Chosen Method: MACS'
        context=build_context({},text,study_context={'requirements':[req(rule={'type':'METHOD_IDENTITY_SINGLE'})]})
        raw=payload(context,text)
        raw['extraction']['steps']=[]
        first=text.index('MACS')
        raw['method_declarations']=[dict(name='MACS',branch='main',span=dict(start=first,end=first+4,quote='MACS'))]
        wrong=apply_assessment(raw,context,text)
        self.assertEqual(wrong['method_identity']['status'],'UNRESOLVED')
        last=text.rindex('MACS')
        raw['method_declarations'][0]['span']=dict(start=last,end=last+4,quote='MACS')
        right=apply_assessment(raw,context,text)
        self.assertEqual(right['method_identity']['status'],'SATISFIED')

    def test_method_declaration_must_cover_every_extraction_alternative(self):
        text='Use MACS.\nUse CUBIC.'
        context=build_context({},text,study_context={'requirements':[req(rule={'type':'METHOD_IDENTITY_SINGLE'})]})
        raw=payload(context,text)
        raw['extraction']['steps']=[]
        raw['extraction']['branches']=[dict(id=branch,mode='ALTERNATIVE',sample_id='same',spans=[{'quote':line}])
            for branch,line in [('A','Use MACS.'),('B','Use CUBIC.')]]
        raw['method_declarations']=[dict(name='MACS',branch='A',span={'quote':'MACS'})]
        result=apply_assessment(raw,context,text)
        self.assertEqual(result['method_identity']['status'],'UNDER_SPECIFIED')
        self.assertNotEqual(result['requirement_results'][0]['effective_status'],'SATISFIED')

    def test_invalid_protocol_quote_guard_is_not_overridden_by_literal_rule(self):
        text='clearing 24 h'
        context=build_context({},text,study_context={'requirements':[req(rule={'type':'LITERAL_REQUIRED','text':'clearing'})]})
        raw=payload(context,text)
        raw['assessment']['requirements'][0]['quotes']=['not an original source quotation']
        result=apply_assessment(raw,context,text)
        record=result['requirement_results'][0]
        self.assertEqual(record['verification']['status'],'SATISFIED')
        self.assertEqual(record['effective_status'],'UNRESOLVED')
        self.assertIn('INVALID_PROTOCOL_QUOTATION',record['guards'])
        self.assertEqual(record['quotes'],raw['assessment']['requirements'][0]['quotes'])

    def test_whole_selected_declaration_has_derived_name_span_without_raw_changes(self):
        text='**Chosen Method:** MACS\nclearing 24 h'
        context=build_context({},text,study_context={'requirements':[req(rule={'type':'METHOD_IDENTITY_SINGLE'})]})
        raw=payload(context,text)
        raw['method_declarations']=[dict(name='MACS',branch='main',span={'quote':'**Chosen Method:** MACS'})]
        before=deepcopy(raw)
        result=apply_assessment(raw,context,text)
        declaration=result['method_identity']['declarations'][0]
        self.assertEqual(result['method_identity']['status'],'SATISFIED')
        self.assertEqual(declaration['span']['quote'],'**Chosen Method:** MACS')
        self.assertEqual(declaration['name_span']['quote'],'MACS')
        self.assertEqual(text[declaration['name_span']['start']:declaration['name_span']['end']],'MACS')
        self.assertEqual(raw,before)

    def test_real_registry_snapshots_load_without_semantic_certification(self):
        c=build_context({'question':'existing DiI, clearing only'},'clearing 24 h')
        self.assertGreaterEqual(len(c['cards']),10)
        self.assertEqual(apply_assessment(payload(c),c,'clearing 24 h')['scientific_applicability_decision']['status'],'UNRESOLVED')


    def test_task_constraints_trace_question_and_replacement(self):
        question={'question':'Already fixed; do not repeat fixation. Labeling completed and QC passed; do not relabel. Use a replacement sample; never restore old signal.'}
        c=build_context(question,'MACS: clearing 24 h',workspace=Path('not_existing'))
        ids={r['id'] for r in c['requirements']}
        self.assertTrue({'FIXATION_SCOPE','COMPLETED_LABEL_QC_SCOPE','REPLACEMENT_SAMPLE_SCOPE','SINGLE_METHOD_IDENTITY'}<=ids)
        for r in c['requirements']:
            if 'question_span' in r:
                sp=r['question_span'];self.assertEqual(question['question'][sp['start']:sp['end']],sp['quote'])
        raw=payload(c,'MACS: clearing 24 h')
        raw['method_declarations']=[dict(name='MACS',branch='main',span={'quote':'MACS'})]
        result=apply_assessment(raw,c,'MACS: clearing 24 h')
        self.assertEqual(result['method_identity']['status'],'SATISFIED')
        self.assertEqual(result['text_completeness_decision']['status'],'SATISFIED')
        self.assertIsNone(result['scientific_gold'])

    def test_selected_method_missing_or_spliced_cannot_qualify_route(self):
        rs=[req('A',rule={'type':'LITERAL_REQUIRED','text':'clearing'},scope='ROUTE',route_id='main')]
        text='MACS and CUBIC: clearing 24 h'
        c=build_context({},text,study_context={'requirements':rs,'route_methods':{'main':'MACS'}})
        raw=payload(c,text)
        self.assertEqual(apply_assessment(raw,c,text)['route_results'][0]['status'],'UNRESOLVED')
        raw['method_declarations']=[dict(name=n,branch='main',span={'quote':n}) for n in ['MACS','CUBIC']]
        result=apply_assessment(raw,c,text)
        self.assertEqual(result['method_identity']['status'],'VIOLATED')
        self.assertNotEqual(result['route_results'][0]['status'],'SATISFIED')
        raw['method_declarations']=raw['method_declarations'][:1]
        self.assertNotEqual(apply_assessment(raw,c,text)['route_results'][0]['status'],'SATISFIED')

    def test_literal_cross_entity_dimension_and_polarity_refused(self):
        context,raw,text=literal_case()
        for field,value in [('entity','OTHER'),('dimension','temperature'),('polarity','NEGATED')]:
            bad=deepcopy(context)
            task={k:bad[k] for k in ['requirements','cards']}
            task['requirements'][0]['literal_rule'][field]=value
            c=build_context({},text,study_context=task)
            with self.assertRaises(ValueError):apply_assessment(payload_with_ri(c,raw['extraction']),c,text)
        task={k:deepcopy(context[k]) for k in ['requirements','cards']}
        task['requirements'][0]['literal_rule']={'type':'SOURCE_LITERAL_EQUALITY','source_id':'C','passage_id':'P','expected':'1.51','observed':'1.53'}
        c=build_context({},text,study_context=task)
        with self.assertRaises(ValueError):apply_assessment(payload_with_ri(c,raw['extraction']),c,text)

    def test_positive_repeat_not_negative_statement_flagged(self):
        for operation,polarity,expected in [('repeat fixation','AFFIRMED','VIOLATED'),('no repeat fixation','NEGATED','SATISFIED')]:
            text=operation+' 24 h'
            c=build_context({'question':'Already fixed; do not repeat fixation.'},text,workspace=Path('not_existing'))
            raw=payload(c,text)
            row=raw['extraction']['steps'][0]
            row.update(phase=operation,operation=operation,quote=text,assertion={'polarity':polarity})
            for field in ['phase','operation']:
                row['field_support'][field]=dict(kind='EXPLICIT',raw_value=operation,spans=[{'quote':operation}],transform='IDENTITY')
            result=apply_assessment(raw,c,text)
            record=next(r for r in result['requirement_results'] if r['id']=='FIXATION_SCOPE')
            self.assertEqual(record['effective_status'],expected)

    def test_other_method_in_actual_operation_is_not_certified_single_route(self):
        text='MACS: clearing 24 h; CUBIC treatment'
        c=build_context({},text,study_context={'requirements':[req(rule={'type':'LITERAL_REQUIRED','text':'clearing'})]})
        raw=payload(c,text)
        row=deepcopy(raw['extraction']['steps'][0])
        row.update(id='S2',phase='CUBIC treatment',operation='CUBIC treatment',duration_text=None,quote='CUBIC treatment')
        row['field_support']={f:dict(kind='EXPLICIT',raw_value='CUBIC treatment',transform='IDENTITY',spans=[{'quote':'CUBIC treatment'}]) for f in ['phase','operation']}
        row['field_support']['duration_text']=dict(kind='MISSING',raw_value=None,spans=[])
        raw['extraction']['steps'].append(row)
        raw['method_declarations']=[dict(name='MACS',branch='main',span={'quote':'MACS'})]
        result=apply_assessment(raw,c,text)
        self.assertEqual(result['method_identity']['status'],'UNRESOLVED')
        self.assertEqual(result['method_identity']['operation_method_conflicts'],['S2'])


    def test_declared_method_retrieval_preserves_contradictory_primary_evidence(self):
        c=build_context({},'**Chosen Method:** MACS\nMACS is methanol-based; compared with FDISCO.')
        self.assertEqual(c['retrieval']['selected_source_ids'],['MACS_ADVSCI_2020'])
        self.assertEqual(len(c['audit_cards']),10)
        self.assertEqual(len(c['retrieval']['unselected_source_ids']),9)
        self.assertIn('Rapid Aqueous Clearing',c['prompt'])
        self.assertNotIn('source_document":{"text":',c['prompt'])
        self.assertTrue(all(s['source_sha256'] and s['card_sha256'] for s in c['retrieval']['source_inventory']))

    def test_unknown_active_alternative_and_explicit_context_not_pruned(self):
        for text in ['**Chosen Method:** MACS + CUBIC','**Chosen Method:** MACS\nthen CUBIC treatment','No selected method']:
            c=build_context({},text)
            self.assertEqual(len(c['cards']),10)
            self.assertTrue(c['retrieval']['fallback_reasons'])
        all_context=build_context({},'No selected method')
        c=build_context({},'**Chosen Method:** MACS',study_context={'requirements':[req()], 'cards':all_context['cards']})
        self.assertEqual(len(c['cards']),10)
        self.assertEqual(c['retrieval']['policy'],'explicit-frozen-cards-preserved')

    def test_actual_q4_prompt_lengths(self):
        import json
        base=Path(r'D:\Code\evaluator-development-runs\model_benchmark_2026-10-02')
        path=base/'qwen38_q4_remote_r2/qwen38_answers.json'
        if not path.exists():self.skipTest('Local archived actual candidate artifacts unavailable')
        answers=json.loads(path.read_text(encoding='utf-8'))['results']
        questions=json.loads((Path(__file__).resolve().parents[1]/'dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json').read_text(encoding='utf-8'))
        for row in answers:
            q=next(q for q in questions if q['question_id']==row['question_id'])
            c=build_context(q,row['content'])
            self.assertEqual(c['retrieval']['selected_source_ids'],['MACS_ADVSCI_2020'])
            self.assertLess(len(c['prompt']),26000)  # Lossless record index adds input overhead; this is not a token budget claim.
            self.assertEqual(len(c['audit_cards']),10)

if __name__=='__main__':unittest.main()