"""Occurrence-scoped label adapter and explicit post-hoc public-data diagnostic.

The frozen converter/KB/arithmetic are not edited. Source-native identity is an
old-interface serialization, not an inferred biological target. No model calls.
"""
from __future__ import annotations
import argparse,ast,contextlib,copy,csv,hashlib,io,json,re,sys
from pathlib import Path

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_grounded_extraction_v11 as ground
import cce_grounded_offline_scoring_v1 as numeric

VERSION='label-occurrence-projection-v1-posthoc'
OUT=ROOT/'artifacts/cce_validation/optimizer_round2_20261010/label_occurrence_diagnostic_v1'
ROUND=OUT.parent
CHANNELS=['s_target_match','s_marker_fluor_compat','s_method_fluor_compat']

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def small_span(s):return {k:s[k] for k in ('unit_id','start','end','quote','answer_sha256')}

def _explicit_nonuse(entity):
    """Only an actual negated/alternative/conditional occurrence is excluded."""
    s=entity['name'];text=s['context'];pos=s['start']-s['context_start']
    cuts=[0]+[m.end() for m in re.finditer(r'[,;\n]|[.!?]\s+',text)]+[len(text)]
    clause=next((text[a:b] for a,b in zip(cuts,cuts[1:]) if a<=pos<b),text)
    neg=bool(re.search(r"\b(?:do\s+not|don['’]t|never|without|not\s+used|not\s+selected|avoid|omit)\b|不使用|不采用",clause,re.I))
    alternative=bool(re.search(r'\b(?:either|alternative|optional|if|unless)\b|备选|可选|如果',clause,re.I))
    return {'excluded':entity['usage'] in ('negated','alternative') or neg or alternative,
      'raw_nonuse_role':entity['usage'] in ('negated','alternative'),
      'explicit_negation':neg,'explicit_alternative_or_condition':alternative,'local_clause':clause}

def _question_native_context(entity,case):
    """Reuse an explicitly named native signal from the fixed task context."""
    if case is None:return {'supported':False,'source':'question_not_supplied'}
    text=case['specific_question'];name=entity['literal_name'];literal=re.escape(name)
    native=r'(?:内源(?:性)?|原生|(?i:native|endogenous|intrinsic))'
    patterns=[r'(?<![A-Za-z0-9_+\-])'+literal+r'(?![A-Za-z0-9_+\-])\s*'+native,
        native+r'\s*'+literal+r'(?![A-Za-z0-9_+\-])']
    evidence=[]
    for pattern in patterns:
        for match in re.finditer(pattern,text):
            prefix=text[max(0,match.start()-24):match.start()]
            negated=bool(re.search(r'(?:\bnot|\bwithout|\bno)\s*$|(?:不使用|不用|非|无)\s*$',prefix,re.I))
            left=max([m.end() for m in re.finditer(r'[,;，；。\n]',text[:match.start()])]+[0])
            right=re.search(r'[,;，；。\n]',text[match.end():])
            clause=text[left:match.end()+right.start()] if right else text[left:]
            optional=bool(re.search(r'\b(?:optional|may|if|unless)\b|for example|such as|e\.g\.|可选|例如|比如|如果',clause,re.I))
            if not negated and not optional:evidence.append({'start':match.start(),'end':match.end(),'quote':match.group()})
    changed_in_answer=[]
    for clause in re.split(r'[.;\n。；]',case['model_response']):
        if name in clause and re.search(r'antibody[- ]only|only\s+(?:anti-|antibod)|仅抗体|只用抗体|不保留[^，,]*(?:内源|原生)|(?:native|endogenous|intrinsic)[^,]*(?:not\s+retained|lost|absent)',clause,re.I):
            changed_in_answer.append(clause.strip())
    return {'supported':bool(evidence),'source':'fixed_original_question',
        'question_sha256':ground.rawsha(text),'exact_native_declarations':evidence,
        'answer_explicit_change_statements':changed_in_answer,
        'answer_preserves_given_identity':not changed_in_answer,
        'biological_preservation_claimed':False,'new_cellular_target_inferred':False}

def derive_label_projection(conversion,doc,case=None):
    """Return source-occurrence pairs; do not mutate conversion or infer targets.

    Accepted local edges retain their actual endpoint identities. An unresolved
    edge creates its own unknown pair. The same literal elsewhere is not a join.
    Source-supported native/selected evidence is a separate axis from raw kind
    and raw occurrence usage. All such corrections are explicit in this result.
    """
    audit=conversion['source_audit'];g=audit['resolved']
    if audit['source_binding']['answer_sha256']!=doc['answer_sha256']:
        raise ValueError('SOURCE_DOCUMENT_MISMATCH')
    if case is not None and ground.source_id_for_case(case)!=doc['source_id']:
        raise ValueError('QUESTION_ANSWER_BINDING_MISMATCH')
    entities={e['id']:e for e in g['entities']}
    pairs=[];occurrences=[];native_audit=[];retained_relations=[]
    native_by_id={}
    for record in g['intrinsic_signals']:
        entity=entities[record['entity_id']];policy=record['identity_policy']
        question_native=_question_native_context(entity,case)
        # These are already source-resolved checks, independent of raw kind/use.
        source_valid=(record['status']=='source_declared' and
          policy['atomic_name_projection_eligible'] and policy['complete_name_occurrence'] and
          (policy['native_source_cue'] or (question_native['supported'] and question_native['answer_preserves_given_identity'])) and policy['affirmative_use_context'] and
          not policy['disqualified_by_capability_alternative_or_negation'] and
          not policy['source_conflicts'] and not policy['conditional_identity_context'])
        # A real competing edge at THIS occurrence conflicts with single native
        # identity serialization. A mentioned duplicate or unknown target does not.
        competing=[r['id'] for r in g['relations'] if r['fluor_entity_id']==entity['id'] and
          r['projection_allowed'] and r['target_entity_id'] and
          entities[r['target_entity_id']]['literal_name']!=entity['literal_name']]
        nonuse=_explicit_nonuse(entity)
        allowed=source_valid and not competing and not nonuse['excluded']
        row={'record_id':record['id'],'entity_id':entity['id'],
          'literal_name':entity['literal_name'],'raw_kind':entity['kind'],'raw_usage':entity['usage'],
          'source_declared_signal_mode':'native' if source_valid else 'unresolved',
          'native_identity_encoding_allowed':allowed,'competing_same_occurrence_edges':competing,
          'original_native_gate_allowed':policy['projection_allowed'],
          'original_literal_collisions_retained_as_metadata':policy['literal_identity_collisions'],
          'fixed_question_native_context':question_native,
          'local_nonuse_audit':nonuse,
          'evidence':small_span(record['evidence']),
          'identity_encoding_not_biological_target_inference':True}
        native_audit.append(row)
        if allowed:native_by_id.setdefault(entity['id'],[]).append(row)
    explicit_unresolved=[]
    if g['coverage']['entities']!='complete':
        explicit_unresolved.append({'kind':'reported_entity_coverage','state':g['coverage']['entities']})
    for row in native_audit:
        entity=entities[row['entity_id']]
        relevant=(entity['usage'] in ('used','unknown') or
            ground.affirmative_entity_use(entity['literal_name'],entity['name']['context']) or
            any(r['fluor_entity_id']==entity['id'] and r['projection_allowed'] for r in g['relations']))
        if not row['native_identity_encoding_allowed'] and relevant and not row['local_nonuse_audit']['excluded']:
            explicit_unresolved.append({'kind':'reported_unresolved_native_record','record_id':row['record_id'],'entity_id':row['entity_id']})
    for entity in g['entities']:
        name=entity['literal_name'];eid=entity['id']
        if entity['kind'] not in ('fluorophore','fluorescent_protein') and eid not in native_by_id:
            # Reagents are often returned as kind=unknown. A record is a concrete
            # label gap only if the answer actually places it in a label field or
            # the model connects it as a fluor endpoint; no hypothetical gap.
            label_context=bool(re.search(r'(?:chosen|selected)\s+(?:label(?:l?ing)?|marker|signal)s?\s*:',entity['name']['context'],re.I))
            fluor_endpoint=any(r['fluor_entity_id']==eid for r in g['relations'])
            if entity['kind']=='unknown' and entity['usage'] in ('used','unknown') and (label_context or fluor_endpoint):
                explicit_unresolved.append({'kind':'reported_unknown_label_entity','entity_id':eid,'literal_name':name})
            continue
        if not entity['name_binding']['atomicity']['projection_eligible_provisional']:
            explicit_unresolved.append({'kind':'reported_nonatomic_label_identity','entity_id':eid,'literal_name':name})
            continue
        related=[r for r in g['relations'] if r['fluor_entity_id']==eid]
        supported=[r for r in related if r['projection_allowed']]
        source_affirmative=ground.affirmative_entity_use(name,entity['name']['context'])
        # A known supported use/pair is retained; an asserted used but unresolved
        # occurrence remains represented rather than disappearing from the graph.
        nonuse=_explicit_nonuse(entity)
        included=(entity['usage']=='used' or source_affirmative or bool(supported) or eid in native_by_id) and not nonuse['excluded']
        role='native_selected' if eid in native_by_id else 'source_supported_use' if source_affirmative or supported else 'raw_used_unresolved' if included else 'context_only'
        occurrence={'entity_id':eid,'literal_name':name,'span':small_span(entity['name']),
          'raw_kind':entity['kind'],'raw_usage':entity['usage'],'derived_role':role,
          'included_as_used_instance':included,'source_affirmative_use':source_affirmative,
          'local_nonuse_audit':nonuse,
          'same_name_other_occurrences_not_inherited':True}
        occurrences.append(occurrence)
        if not included:continue
        targets={entities[r['target_entity_id']]['literal_name'] for r in supported if r['target_entity_id']}
        conflict=len(targets)>1
        for r in related:
            target=entities[r['target_entity_id']]['literal_name'] if r['target_entity_id'] else None
            valid=bool(r['projection_allowed'] and not conflict)
            pairs.append({'pair_id':'relation:'+r['id'],'entity_id':eid,'fluor_literal':name,
              'marker_literal':target if valid else None,'reported_target_literal':target,
              'scope':'this_source_occurrence_only','kind':'supported_relation' if valid else 'unresolved_relation',
              'raw_relation_status':r['status'],'original_local_gate_allowed':r['projection_allowed'],
              'same_occurrence_distinct_target_conflict':conflict,'evidence':small_span(r['evidence']),
              'target_propagated_to_other_occurrence':False})
            if not valid:explicit_unresolved.append({'kind':'reported_unresolved_relation','relation_id':r['id'],'entity_id':eid})
            retained_relations.append(r['id'])
        for native in native_by_id.get(eid,[]):
            pairs.append({'pair_id':'native:'+native['record_id'],'entity_id':eid,'fluor_literal':name,
              'marker_literal':name,'reported_target_literal':None,'scope':'this_source_occurrence_only',
              'kind':'source_native_identity_encoding','evidence':native['evidence'],
              'target_propagated_to_other_occurrence':False,'biological_target_inferred':False})
        if not related and eid not in native_by_id:
            pairs.append({'pair_id':'unresolved_entity:'+eid,'entity_id':eid,'fluor_literal':name,
              'marker_literal':None,'reported_target_literal':None,'scope':'this_source_occurrence_only',
              'kind':'source_key_only','evidence':small_span(entity['name']),
              'target_propagated_to_other_occurrence':False})
    # Retain a supported-only view for inspection. It is never called the full
    # dictionary when another occurrence remains unknown or has another target.
    names=sorted({p['fluor_literal'] for p in pairs});local_view={};losses=[]
    for name in names:
        rows=[p for p in pairs if p['fluor_literal']==name]
        known={p['marker_literal'] for p in rows if p['marker_literal'] is not None}
        unknown=[p['pair_id'] for p in rows if p['marker_literal'] is None]
        if len(known)==1:local_view[name]=next(iter(known))
        elif not known:local_view[name]=''
        if len(known)>1 or unknown:
            losses.append({'literal_name':name,'supported_targets':sorted(known),
              'unresolved_pair_ids':unknown,'single_value_cannot_represent_full_occurrence_graph':True})
    return {'version':VERSION,'source_binding':copy.deepcopy(audit['source_binding']),
      'occurrences':occurrences,'pairs':pairs,'native_audit':native_audit,
      'raw_relation_count':len(g['relations']),'retained_selected_relation_ids':retained_relations,
      'original_marker_dict':copy.deepcopy(conversion['legacy_projection']['extraction']['marker_dict']),
      'supported_local_dictionary_view':local_view,'single_value_projection_losses':losses,
      'lossless_single_value_projection':not losses,
      'explicit_label_uncertainties':explicit_unresolved,
      'raw_modified':False,'source_aliases_added':False,'expert_validated':False}

def _original_nullable_min(original_runner):
    """Compile exactly the original nested helper, not a new aggregation rule."""
    path=Path(original_runner.__file__)
    module=ast.parse(path.read_text(encoding='utf-8'))
    outer=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='calculate_effectiveness_score')
    node=next(n for n in outer.body if isinstance(n,ast.FunctionDef) and n.name=='nullable_min')
    ns={};exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),ns)
    return ns['nullable_min'],hashlib.sha256(ast.dump(node).encode()).hexdigest()

def _publish_label(original_label,explicit_uncertainties):
    return None if explicit_uncertainties and original_label not in (None,0) else original_label

def score_label_occurrences(projection,original_runner,quantitative,demand,targets):
    """Evaluate each true occurrence with unchanged EGES and aggregate its pairs.

    Original per-pair target/compatibility operations and nullable_min are reused;
    duplicate names need no fabricated dictionary keys. Unknown pairs remain as
    nullable target/marker channels and retain independently known method values.
    """
    nullable_min,helper_sha=_original_nullable_min(original_runner)
    rows=[]
    for pair in projection['pairs']:
        marker=pair['marker_literal'] or ''
        one={pair['fluor_literal']:marker}
        replay=original_runner.calculate_effectiveness_score(quantitative,demand,
          original_runner.MODEL_SPACE_SIGNED,one,targets)
        processed=original_runner._preprocess_marker_dict(one)[0]
        marker_present=any(bool(m) for _,m in processed)
        rows.append({'pair_id':pair['pair_id'],'kind':pair['kind'],'original_function_input':one,
          'channels':{k:replay[k] for k in CHANNELS},'local_s_label':replay['s_label'],
          'contribution_present':{'s_target_match':marker_present,'s_marker_fluor_compat':marker_present,
             's_method_fluor_compat':replay['method_identity']['status']=='RESOLVED_SINGLE'},
          'marker_identity_conflict':any(original_runner.marker_identity_conflict(m) for _,m in processed),
          'compatibility_audit':replay['compatibility_audit']})
    identity_unresolved=any(r['marker_identity_conflict'] for r in rows)
    channels={key:nullable_min([r['channels'][key] for r in rows if r['contribution_present'][key]]) for key in CHANNELS}
    if identity_unresolved:channels['s_target_match']=None
    original_label=nullable_min(list(channels.values()))
    # Explicitly declared incomplete label evidence is not a complete nonzero
    # score. The original bounded-minimum zero still determines the scalar.
    uncertainties=projection.get('explicit_label_uncertainties',[])
    label=_publish_label(original_label,uncertainties)
    witnesses=[{'pair_id':r['pair_id'],'channel':k,'value':0.0} for r in rows for k in CHANNELS
      if r['channels'][k]==0 and not (k=='s_target_match' and identity_unresolved)]
    if projection['lossless_single_value_projection']:
        whole=original_runner.calculate_effectiveness_score(quantitative,demand,
          original_runner.MODEL_SPACE_SIGNED,projection['supported_local_dictionary_view'],targets)
        for key in CHANNELS:
            if not numeric.same(whole[key],channels[key]):raise AssertionError('LOSSLESS_CHANNEL_MISMATCH:'+key)
        if not numeric.same(whole['s_label'],original_label):raise AssertionError('LOSSLESS_LABEL_MISMATCH')
    return {'version':VERSION,'channels':channels,'s_label':label,'original_occurrence_numeric_label':original_label,'pair_results':rows,
      'explicit_label_uncertainties':uncertainties,
      'publication_note':'explicit unresolved nonzero whole-label evidence' if label is None and original_label is not None else None,
      'original_identity_unresolved':identity_unresolved,'zero_witnesses':witnesses,
      'nullable_min_original_AST_sha256':helper_sha,'original_function_file':str(original_runner.__file__),
      'original_function_file_sha256':sha(original_runner.__file__),
      'single_value_projection_complete':projection['lossless_single_value_projection'],
      'unknown_pairs_retained':sum(p['marker_literal'] is None for p in projection['pairs']),
      'finite_zero_is_not_complete_graph':label==0 and not projection['lossless_single_value_projection'],
      'new_KB_values':False,'biological_target_inferred':False,'model_calls':0}

def load_public(phase,aid):
    directory=ROUND/phase
    if phase not in ('grounded_development_v11','grounded_controls_v11'):raise ValueError('PUBLIC_PHASE_ONLY')
    matrix=read(directory/'matrix.json');row=next(r for r in matrix if r['anonymous_answer_id']==aid)
    trialpath=directory/'run/trials'/f"{row['planned_trial_id']}.json";trial=read(trialpath)
    if trial['status']!='success':raise ValueError('THIS_DIAGNOSTIC_REQUIRES_COMMITTED_SUCCESS')
    cases=read(directory/'cases.json');cases=cases['cases'] if isinstance(cases,dict) else cases
    case=next(c for c in cases if c['case_id']==row['case_id'])
    doc=read(directory/'source_documents'/f'{aid}.json')
    cv=trial['evaluation']['grounded_extraction_v11']['conversion']
    if ground.rawsha(case['model_response'])!=doc['answer_sha256']:raise ValueError('CASE_BINDING')
    for group in ['entities','method_mentions']:
        for entity in cv['source_audit']['resolved'][group]:
            s=entity['name']
            if doc['text'][s['start']:s['end']]!=s['quote']:raise ValueError('EXACT_SOURCE_BINDING')
    return case,doc,cv,trial['evaluation']['numeric_result'],row,[directory/'cases.json',directory/'matrix.json',trialpath,directory/'source_documents'/f'{aid}.json']

def software_checks(runner,demand,quant,targets):
    checks=[]
    # Tests use existing names only as inputs to the unchanged numeric function;
    # no scientific compatibility values or aliases are introduced.
    for mapping in ({},{'GFP':'GFP'},{'DAPI':''},{'GFP':'GFP','DAPI':''},{'Alexa Fluor':'MAP2'},{'Alexa Fluor':'MAP2','DAPI':''}):
        p={'pairs':[{'pair_id':str(i),'kind':'software','fluor_literal':k,'marker_literal':v or None}
          for i,(k,v) in enumerate(mapping.items())],
          'lossless_single_value_projection':True,'supported_local_dictionary_view':mapping}
        test_targets=[{'marker_name':'MAP2'}] if mapping=={'Alexa Fluor':'MAP2','DAPI':''} else targets
        value=score_label_occurrences(p,runner,quant,demand,test_targets)
        whole=runner.calculate_effectiveness_score(quant,demand,runner.MODEL_SPACE_SIGNED,mapping,test_targets)
        checks.append({'name':'single_value_exact_original_'+str(len(checks)),
          'pass':all(numeric.same(value['channels'][k],whole[k]) for k in CHANNELS) and numeric.same(value['s_label'],whole['s_label'])})
    f,_=_original_nullable_min(runner)
    checks += [{'name':'original_min_zero_and_unknown','pass':f([0,None])==0},
      {'name':'original_min_nonzero_and_unknown','pass':f([6,None]) is None},
      {'name':'explicit_partial_nonzero_not_whole_label','pass':_publish_label(6,[{'kind':'reported_entity_coverage'}]) is None},
      {'name':'explicit_partial_reliable_zero_preserved','pass':_publish_label(0,[{'kind':'reported_entity_coverage'}])==0}]
    for text,usage,expected in [('do not use SYN_X','used',True),('Use SYN_X as an alternative','used',True),
          ('Selected Labeling: SYN_X','alternative',True),('Chosen Labeling: SYN_X','used',False)]:
        pos=text.index('SYN_X');e={'usage':usage,'name':{'context':text,'context_start':0,'start':pos}}
        checks.append({'name':'nonuse_'+str(len(checks)),'pass':_explicit_nonuse(e)['excluded']==expected})
    if not all(c['pass'] for c in checks):raise AssertionError('SOFTWARE_CHECK_FAILED')
    return checks

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['run-public'])
    parser.add_argument('--out',type=Path,default=OUT/'revision03')
    args=parser.parse_args()
    out=args.out.resolve()
    if not out.is_relative_to(OUT.resolve()):raise ValueError('OUTPUT_WITHIN_DIAGNOSTIC_ONLY')
    if (out/'results.json').exists():raise ValueError('OUTPUT_ALREADY_EXISTS_USE_NEW_VERSION')
    with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):runner,registry=numeric.runtime()
    results=[];bindings=[];checks=[]
    for phase,aid in [('grounded_controls_v11','E2_09'),('grounded_development_v11','A01')]:
        case,doc,cv,old,row,paths=load_public(phase,aid)
        demand=registry.get(case['question_id'],case['specific_question'])
        meta=runner.QUESTION_META_KB[registry.questions[str(case['question_id'])]['question_id']]
        quantitative=copy.deepcopy(old['quantitative_data']);targets=meta.get('marker_query_targets') or []
        # Verify this environment reproduces the archived, original formula first.
        baseline=runner.calculate_effectiveness_score(quantitative,demand,runner.MODEL_SPACE_SIGNED,
          cv['legacy_projection']['extraction']['marker_dict'],targets)
        for key in numeric.EGES+CHANNELS:
            if not numeric.same(baseline[key],old['original_EGES_replay'][key]):raise AssertionError('ARCHIVE_NUMERIC_DRIFT:'+key)
        projected=derive_label_projection(cv,doc)
        scored=score_label_occurrences(projected,runner,quantitative,demand,targets)
        components=copy.deepcopy(old['component_gated_proposals']);components['s_label']=scored['s_label']
        derived=numeric.derive(components,row['step'],True)
        for key in numeric.DIRECT+['s_method','s_time','s_trans','sr','sp','Com','Cor']:
            if not numeric.same(derived[key],old['metrics'][key]):raise AssertionError('UNRELATED_COMPONENT_CHANGED:'+key)
        results.append({'phase':phase,'anonymous_answer_id':aid,'case_id':case['case_id'],
          'question_id':case['question_id'],'source_binding':cv['source_audit']['source_binding'],
          'original_metrics':old['metrics'],'original_label_channels':{k:baseline[k] for k in CHANNELS},
          'derived_projection':projected,'derived_label':scored,'derived_metrics':derived,
          'original_status_preserved':'success','posthoc_not_new_model_result':True,
          'complete_CCE_derived':all(numeric.finite(derived[k]) for k in ['Com','Cor','Eff','IA','HV']),
          'quantitative_data_unchanged':quantitative,'expert_validated':False})
        bindings += paths
        if not checks:checks=software_checks(runner,demand,quantitative,targets)
    bindings += [Path(__file__),Path(ground.__file__),Path(runner.__file__),Path(numeric.__file__),
      ROOT/'scripts/cce_grounded_development_v7.py',Path(numeric.j.HIST),ROOT/'dataset/Q+AR/src/demand_vectors_all.json']
    result={'status':'posthoc_public_label_adapter_completed','scope':'E2_09 and development A01 only',
      'new_model_calls':0,'source_records_modified':False,'current_scores_replaced':False,
      'confirmation_answers_read':False,'results':results,'software_checks':checks,
      'inputs':[{'path':str(p),'sha256':sha(p)} for p in dict.fromkeys(bindings)],
      'actual_command':[sys.executable,*sys.argv]}
    save(out/'results.json',result)
    rows=[]
    for resultrow in results:
        for key in numeric.METRICS:
            rows.append({'case':resultrow['anonymous_answer_id'],'metric':key,
              'original':resultrow['original_metrics'][key],'posthoc':resultrow['derived_metrics'][key]})
    with (out/'metric_comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['case','metric','original','posthoc']);writer.writeheader();writer.writerows(rows)
    print(json.dumps({'status':result['status'],'checks':len(checks),'results':[{
      'case':r['anonymous_answer_id'],'old_label':r['original_metrics']['s_label'],
      'posthoc_label':r['derived_metrics']['s_label'],'posthoc_Eff':r['derived_metrics']['Eff'],
      'unknown_pairs':r['derived_label']['unknown_pairs_retained'],
      'complete_CCE_derived':r['complete_CCE_derived']} for r in results]},ensure_ascii=True))

if __name__=='__main__':main()
