"""Source-explicit non-core time exclusions under the unchanged rubric 3.2.

Derives support for already-returned labeling_preparation records and classifies
an omitted mounting duration as non-core. No raw phase, operation, number,
duration, repeat, coverage declaration, or missing operation is manufactured.
"""
from __future__ import annotations
import argparse, copy, contextlib, io, re, sys
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_operation_coverage_scope_diagnostic_v1 as scope
g, j, base, scoring = scope.g, scope.j, scope.base, scope.scoring
OUT = base.BASE / 'noncore_time_scope_fix_v1'
VERSION = 'source-explicit-noncore-time-scope-v1'
require, bind, save_once = scope.require, scope.bind, scope.save_once
CORE = re.compile(r'delipid|decalcif|decolor|dehydrat|clearing\s+(?:reagent|solution|step|treatment|transition)|refractive\s+index\s+match|\bRI\s+match|\bequilibrat|\b(?:DBE|THF|methanol|ethanol|dichloromethane)\b', re.I)
PREP_UNKNOWN = re.compile(r'permeabili|\bDMSO\b|\bblocking\s+solution\b', re.I)
TRANSITION = re.compile(r'\b(?:between|transition|exchange|switch|replace|transfer)\b', re.I)


def source_span(doc, start, end):
    unit = next(u for u in doc['units'] if u['start'] <= start and end <= u['end'])
    return {'unit_id': unit['unit_id'], 'start': start, 'end': end, 'quote': doc['text'][start:end],
        'answer_sha256': doc['answer_sha256'], 'source_id': doc['source_id']}


def support(operation, audit, doc):
    s = operation['operation']; text = s['quote']
    if CORE.search(text) or operation.get('phase_support', {}).get('possible_core_function'):
        return None
    # The original rubric excludes explicit antibody incubation. A named
    # additive in its buffer does not turn that declared action into clearing.
    if re.search(r'\bincubat\w*\s+with\s+(?:(?:primary|secondary)\s+)?antibod(?:y|ies)\b|\b(?:antibody|immuno)[- ]?stain\w*\b', text, re.I):
        return {'basis': 'explicit_source_antibody_staining_action', 'evidence': [copy.deepcopy(s)]}
    if PREP_UNKNOWN.search(text):
        return None
    pbs = bool(re.search(r'\bPBS\b|phosphate[- ]buffered\s+saline', text, re.I))
    removal = bool(re.search(r'\bremove\b|\bwash\s+(?:out|away)\b|\brinse\s+(?:out|away)\b', text, re.I))
    if pbs and removal and not TRANSITION.search(text):
        if re.search(r'\b(?:residual|remaining|excess)\s+fixative\b', text, re.I):
            return {'basis': 'routine_PBS_removal_of_residual_fixative', 'evidence': [copy.deepcopy(s)]}
        if re.search(r'\b(?:excess|residual|unbound)\b', text, re.I) and re.search(r'\b(?:dye|stain)\b', text, re.I):
            return {'basis': 'routine_PBS_removal_of_excess_dye', 'evidence': [copy.deepcopy(s)]}
    if re.search(r'\b(?:stain(?:ing)?|counterstain(?:ing)?)\s+(?:with|using)\b|\bincubat\w*\b.*\b(?:dye|stain)\b', text, re.I):
        return {'basis': 'explicit_source_staining_action', 'evidence': [copy.deepcopy(s)]}
    if not re.search(r'\bincubat\w*\s+with\b', text, re.I): return None
    # Open source names: their dye role must also be stated literally in this
    # answer. No name dictionary, case ID or compatibility score is consulted.
    for entity in audit['resolved'].get('entities', []):
        name = entity['name']['quote']
        if not entity.get('name_binding', {}).get('atomicity', {}).get('projection_eligible_provisional', False): continue
        if not re.search(r'(?<![\w-])' + re.escape(name) + r'(?![\w-])', text): continue
        role = re.compile(r'(?<![\w-])' + re.escape(name) + r'\s+(?:dye|stain)\b|\b(?:dye|stain)\s+' + re.escape(name) + r'(?![\w-])', re.I)
        for m in role.finditer(doc['text']):
            evidence = source_span(doc, m.start(), m.end())
            return {'basis': 'incubation_with_source_explicit_dye_identity', 'entity_id': entity['id'],
                'source_name': name, 'evidence': [copy.deepcopy(s), evidence]}
    return None


def explicit_mounting_only(text):
    return bool(re.search(r'\bmount(?:ing)?\b', text, re.I)
        and re.search(r'\b(?:chamber|holder|coverslip|slide)\b', text, re.I)
        and not re.search(r'delipid|decalcif|decolor|dehydrat|clearing\s+(?:treatment|step|process|incubation)|refractive\s+index\s+match|\bRI\s+match|\bincubat|\bequilibrat|\bpermeabili', text, re.I))


def derive_audit(original, doc):
    require(original['source_binding']['source_id'] == doc['source_id']
        and original['source_binding']['answer_sha256'] == doc['answer_sha256']
        and g.rawsha(doc['text']) == doc['answer_sha256'], 'SOURCE_IDENTITY_MISMATCH')
    audit = copy.deepcopy(original); changes = []; units = {u['unit_id']:u for u in doc['units']}
    for op in audit['resolved']['operations']:
        s = op['operation']; require(doc['text'][s['start']:s['end']] == s['quote'], 'OPERATION_SOURCE_SPAN_CHANGED')
        if op['phase'] != 'labeling_preparation' or op['phase_support']['supported']: continue
        why = support(op, original, doc)
        if why:
            old = copy.deepcopy(op['phase_support']); op['phase_support']['supported'] = True
            op['phase_support']['source_explicit_noncore_support'] = why
            op['phase_support']['original_phase_support'] = old
            changes.append({'kind':'labeling_phase_support','operation_id':op['id'],'original_support':old,
                'derived_supported':True, 'raw_phase_unchanged':True, **why})
    for row in audit['inventory']:
        if row['kind'] != 'duration' or row['coverage_state'] == 'covered_time_evidence': continue
        s = row['span']; unit = units[s['unit_id']]
        require(doc['text'][s['start']:s['end']] == s['quote'], 'DURATION_SOURCE_SPAN_CHANGED')
        if explicit_mounting_only(unit['text']):
            old = row['coverage_state']; row['kind'] = 'excluded_noncore_duration'
            row['coverage_state'] = 'classified_excluded_noncore_mounting_duration'
            row['original_candidate_kind'] = 'duration'; row['original_coverage_state'] = old
            row['exclusion_evidence'] = source_span(doc, unit['start'], unit['end'])
            row['model_operation_omission_preserved'] = True
            changes.append({'kind':'excluded_noncore_duration','candidate_id':row['candidate_id'],
                'duration_span':copy.deepcopy(s),'source_evidence':row['exclusion_evidence'],
                'original_coverage_state':old,'operation_created':False,'numeric_value_added':False})
    # Only support annotation may change on a returned operation.
    old_resolved = copy.deepcopy(original['resolved']); new_resolved = copy.deepcopy(audit['resolved'])
    for value in [old_resolved,new_resolved]:
        for op in value['operations']: op.pop('phase_support', None)
    require(old_resolved == new_resolved and original['source_binding'] == audit['source_binding'], 'RAW_RESOLVED_DEPENDENCY_CHANGED')
    require([r['candidate_id'] for r in original['inventory']] == [r['candidate_id'] for r in audit['inventory']], 'CANDIDATE_IDS_CHANGED')
    audit['derived_noncore_scope_policy'] = {'version':VERSION,'changes':changes,
        'rubric_scope':'3.2 excludes staining and routine PBS washes; imaging mounting is outside listed core categories',
        'original_phase_duration_repeat_scope_and_coverage_preserved':True,'model_operation_omissions_preserved':True,
        'candidate_registry_unchanged':True,'not_scientific_phase_gold':True}
    return audit, changes


def self_check(out):
    require(not out.exists(), 'NEW_OUTPUT_ONLY'); out.mkdir(parents=True); checks=[]
    cases=[('Incubate with PBS to remove residual fixative.',True),
        ('Incubate with PBS to wash out excess ALPHA dye.',True),
        ('Staining with an unnamed fluorescent dye.',True),
        ('Incubate with PBS to remove residual fixative between clearing reagent steps.',False),
        ('Incubate with permeabilization solution.',False),
        ('Incubate with an unspecified solution.',False)]
    for text, expected in cases:
        doc=g.document(text,'SYNTHETIC_ONLY'); op={'operation':source_span(doc,0,len(text)),
            'phase_support':{'supported':False,'possible_core_function':False}}
        value=support(op,{'resolved':{'entities':[]}},doc)
        ok=bool(value) is expected; checks.append({'text':text,'expected_support':expected,'pass':ok}); require(ok,'PHASE_PROBE')
    for text, expected in [('Pre-imaging mounting in a custom chamber filled with DBE (RI = 1.56).',True),
        ('Mount in a chamber and incubate for refractive index matching.',False),
        ('Equilibrate in a holder before imaging.',False),('Incubate in clearing reagent in a chamber.',False)]:
        ok=explicit_mounting_only(text) is expected; checks.append({'text':text,'expected_noncore':expected,'pass':ok});require(ok,'MOUNTING_PROBE')
    save_once(out/'verification.json',{'status':'pass','software_only':True,'checks':checks,'script':bind(__file__),
        'new_model_requests':0,'actual_command':[sys.executable,*sys.argv]})
    print(j.canonical({'status':'pass','checks':len(checks)}))


def actual(out):
    require(not out.exists(), 'NEW_OUTPUT_ONLY'); out.mkdir(parents=True)
    source=base.BASE/'operation_coverage_scope_batch_v1/actual_execution_01'; results=[]; inputs=[]
    for cohort,aid in [('E2','E2_15'),('E2','E2_16'),('E2','E2_20'),('development','A03')]:
        batch=base.BASE/('grounded_controls_v11' if cohort=='E2' else 'grounded_development_v11')
        cases=j.read(batch/'cases.json')['cases'];case=next(c for c in cases if c['anonymous_answer_id']==aid)
        row=next(r for r in j.read(batch/'matrix.json') if r['anonymous_answer_id']==aid)
        cell_id=row.get('cell_id',aid);folder=source/'cells'/cohort/cell_id
        cvpath=folder/'derived_conversion.json';numpath=folder/'posthoc_numeric.json';docpath=Path(row['assets']['source_document']['path'])
        cv=j.read(cvpath);doc=j.read(docpath);numeric=j.read(numpath)
        require(g.rawsha(case['model_response'])==doc['answer_sha256'],'EXACT_CASE_SOURCE')
        audit,changes=derive_audit(cv['source_audit'],doc);derived=copy.deepcopy(cv);derived['source_audit']=audit
        derived['legacy_projection']=g.project_legacy(audit)
        derived['legacy_runner_payload']={'scores':copy.deepcopy(cv['legacy_runner_payload']['scores']),'extraction':copy.deepcopy(derived['legacy_projection']['extraction'])}
        derived['legacy_runner_content']=g.canonical(derived['legacy_runner_payload'])
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            before=scoring.score_conversion(case,cv,base.BACKEND,row['step']);after=scoring.score_conversion(case,derived,base.BACKEND,row['step'])
        require(before==numeric,'ORIGINAL_NUMERIC_REPLAY')
        require(all(scoring.same(before['metrics'][m],after['metrics'][m]) for m in scoring.DIRECT+['s_method','s_label','s_trans','sr','sp','Com','Cor']),'NON_TIME_NUMERIC_CHANGED')
        result={'cohort':cohort,'anonymous_answer_id':aid,'original_time_hours':cv['legacy_projection']['time_calculation']['total_hours'],
            'derived_time_hours':derived['legacy_projection']['time_calculation']['total_hours'],'original_s_time':before['metrics']['s_time'],
            'derived_s_time':after['metrics']['s_time'],'remaining_issues':derived['legacy_projection']['time_calculation']['issues'],
            'changes':changes,'original_metrics':before['metrics'],'derived_metrics':after['metrics']}
        save_once(out/(aid+'.json'),result);results.append(result)
        inputs.extend([bind(p) for p in [cvpath,numpath,docpath,batch/'cases.json',batch/'matrix.json']])
    base.verify_bindings(inputs)
    summary={'status':'actual_four_case_noncore_scope_replay_complete','new_model_requests':0,'script':bind(__file__),
        'inputs':inputs,'original_raw_and_results_unchanged':True,'results':[{k:r[k] for k in ['cohort','anonymous_answer_id','original_time_hours','derived_time_hours','original_s_time','derived_s_time','remaining_issues']} for r in results],
        'actual_command':[sys.executable,*sys.argv]}
    save_once(out/'summary.json',summary);print(j.canonical({'status':summary['status'],'results':summary['results']}))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['self-check','actual']);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve();require(out.is_relative_to(OUT.resolve()),'NEW_NONCORE_NAMESPACE_ONLY')
    (self_check if a.action=='self-check' else actual)(out)
if __name__=='__main__':main()
