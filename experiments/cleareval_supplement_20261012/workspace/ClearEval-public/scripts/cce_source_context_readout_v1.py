"""Export and independently check the approved source-context comparison.

No model or embedding calls are made. Scientific claims require separate author
review; mechanical source binding alone never certifies a scientific judgment.
"""
import argparse
import contextlib
import hashlib
import io
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT)]
import cce_source_context_validation_runner_v1 as run
import cce_posthoc_source_backend_v3 as ground
from cce_grounded_extraction_fieldwise_base_v1 import _expand_ref
from cce_record_diagnostics_v2 import records_audit

DIRECT = ['c_param', 'co_order', 'co_method', 'co_param', 'co_chem']
CHECKS = []
BINDINGS = {}


def bind(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def read(path, expected=None):
    b = bind(path)
    if expected is not None:
        check(b['sha256'] == expected, 'input_sha256', b['path'])
    BINDINGS[b['path']] = b
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def check(ok, kind, item):
    CHECKS.append({'kind': kind, 'item': str(item), 'passed': bool(ok)})
    if not ok:
        raise AssertionError(kind + ': ' + str(item))


def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def same(a, b):
    return a == b if a is None or b is None else math.isclose(a, b, rel_tol=0, abs_tol=1e-12)


def aggregate(m):
    com = .4*m['sr'] + .6*m['c_param']/3 if finite(m['sr']) and finite(m['c_param']) else None
    cor = sum([m['co_order']/3, m['co_method']/2, m['co_param']/2, m['co_chem']])/4 if all(finite(m[k]) for k in DIRECT[1:]) else None
    eff = sum([(m['s_method']/2.5+1)/2, m['s_label']/6, m['s_trans']/3, m['s_time']/3])/4 if all(finite(m[k]) for k in ['s_method','s_label','s_trans','s_time']) else None
    complete = all(finite(x) for x in [com,cor,eff])
    return {'Com':com,'Cor':cor,'Eff':eff,'IA':min(com,cor,eff) if complete else None,
            'HV':com*cor*eff if complete else None}


def save(path, obj):
    with path.open('x', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')


def main(args):
    out, dest = args.out.resolve(), args.dest.resolve()
    assert not dest.exists(), 'Choose a new readout directory.'
    plan, matrix = run.validate(out)
    budget, _, terminal = run.bound_functions(out)
    authority = budget.authorization()
    counts = budget.counts()
    check(counts['round'] == 10, 'ten_actual_requests', counts['round'])
    check(counts['package'] == 438, 'package_request_count', counts['package'])
    baselines = read(out/'baseline_per_answer.json')
    bycase = {c['case_id']:c for c in read(out/'cases.json')['cases']}
    byanswer = {c['anonymous_answer_id']:c for c in bycase.values()}
    steps = read(out/'steps.json')
    source_rows = []
    for b in baselines:
        case = byanswer[b['answer_id']]
        source_rows.append({'observation_id':b['observation_id'], 'case':case,
            'metrics':b['metrics'], 'status':'archived_success_reused',
            'raw':b['source']['raw'], 'saved_processing':b['source']['current_scoring'],
            'doc':bind(out/'source_documents'/(b['answer_id']+'.json')),
            'new_request':False})
    runtime = []
    for row in matrix:
        t = terminal(out,row)
        attempt = run.original.attempt_path(out,row)
        provider_path = attempt/'provider_response.json'
        if provider_path.exists():
            provider = read(provider_path)
            runtime.append({'observation_id':row['observation_id'],
                'model':provider.get('model'),'done':provider.get('done'),
                'done_reason':provider.get('done_reason'),
                **{k:provider.get(k) for k in ['prompt_eval_count','eval_count','total_duration','load_duration','prompt_eval_duration','eval_duration']}})
        source_rows.append({'observation_id':row['observation_id'], 'case':bycase[row['case_id']],
            'metrics':t['metrics'],'status':t['status'],
            'raw':bind(attempt/'raw_response.txt') if (attempt/'raw_response.txt').exists() else None,
            'saved_processing':bind(attempt/'processing.json') if (attempt/'processing.json').exists() else None,
            'doc':row['assets']['doc'],'new_request':True,
            'terminal':bind(run.original.terminal_path(out,row))})
    source_rows.sort(key=lambda r:r['observation_id'])
    packets, diagnostics, replays, parse_issues, observations = [], [], [], [], []
    for row in source_rows:
        oid, case, m = row['observation_id'], row['case'], row['metrics']
        baseline = next(b for b in baselines if b['answer_id']==oid.split('_')[0])
        for k in ['sr','sp']:
            check(m[k] == baseline['metrics'][k], 'original_step_value_preserved', oid+'/'+k)
        derived = aggregate(m)
        for k, value in derived.items():
            check(same(value,m[k]), 'independent_aggregate', oid+'/'+k)
        observations.append({k:v for k,v in row.items() if k!='case'})
        if row['raw'] is None:
            parse_issues.append({'observation_id':oid,'issue':'provider_raw_absent'})
            continue
        try:
            payload = read(row['raw']['path'], row['raw']['sha256'])
        except json.JSONDecodeError as exc:
            parse_issues.append({'observation_id':oid,'issue':'raw_json_decode','detail':str(exc)})
            continue
        doc = read(row['doc']['path'], row['doc']['sha256'])
        check(doc['answer_sha256'] == case['answer_sha256'], 'answer_identity', oid)
        raw = Path(row['raw']['path']).read_text(encoding='utf-8')
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            replay = run.processor.independent_processing(raw, doc, case, steps[case['case_id']])
        for k in run.original.METRICS:
            check(same(replay['metrics'][k], m[k]), 'primary_v7_replay', oid+'/'+k)
        stored = read(row['saved_processing']['path'], row['saved_processing']['sha256']) if row['saved_processing'] else None
        check(stored is not None and replay['full_conversion_success'] == stored['full_conversion_success'], 'full_conversion_replay', oid)
        replays.append({'observation_id':oid,'full_conversion_success':replay['full_conversion_success'],
            'all_metrics_match':True,'metrics':replay['metrics']})
        local_rows, local_issues, duplicates = records_audit(payload,doc,ground)
        diagnostics.append({'observation_id':oid,'records':local_rows,'issues':local_issues,'duplicates':duplicates})
        for metric in DIRECT:
            group = 'completeness' if metric=='c_param' else 'correctness'
            direct = payload['scores'][group][metric]
            evidence, = [e for e in payload['score_evidence'] if e['m']==metric]
            spans = []
            issues = []
            for ref in evidence['u']:
                try:
                    span = ground.resolve(_expand_ref(ref),doc)
                    check(doc['text'][span['start']:span['end']]==span['quote'], 'answer_citation', oid+'/'+metric+'/'+ref)
                    spans.append(span)
                except (ValueError,KeyError,AssertionError) as exc:
                    issues.append({'reference':ref,'error':str(exc)})
            packets.append({'observation_id':oid,'answer_id':oid.split('_')[0],
                'condition':oid.split('_')[1],'question_id':case['question_id'],'metric':metric,
                'raw_score':direct['score'],'saved_primary_score':m[metric],
                'reasoning':direct['reasoning'],'score_evidence':evidence,
                'resolved_answer_spans':spans,'citation_issues':issues,
                'raw_source':row['raw'],'raw_pointer':'/scores/'+group+'/'+metric,
                'reference_ids':[r['reference_id'] for r in case['references']],
                'expert_adjudicated':False,'scientific_claim_review':'separate_author_review_required'})
    coverage = {}
    for condition in ['K0','K1','K2']:
        subset = [o for o in observations if o['observation_id'].endswith('_'+condition)]
        coverage[condition] = {k:sum(finite(o['metrics'][k]) for o in subset) for k in run.original.METRICS}
    lookup={o['observation_id']:o for o in observations}
    contrasts=[]
    for contrast in read(out/'paired_contrasts.json'):
        a,b=lookup[contrast['left']],lookup[contrast['right']]
        contrasts.append({**contrast,'changes':{k:{'left':a['metrics'][k],'right':b['metrics'][k],
            'delta':b['metrics'][k]-a['metrics'][k] if finite(a['metrics'][k]) and finite(b['metrics'][k]) else None}
            for k in run.original.METRICS}})
    summary={'created_utc':datetime.now(timezone.utc).isoformat(),
        'observations':len(observations),'cached_baselines':5,'new_actual_requests':10,
        'package_requests':counts['package'],'primary_pairs':len(contrasts),
        'direct_evidence_packets':len(packets),'resolved_answer_citations':sum(len(p['resolved_answer_spans']) for p in packets),
        'citation_issues':sum(len(p['citation_issues']) for p in packets),
        'record_diagnostic_issues':sum(len(d['issues']) for d in diagnostics),
        'structural_parse_issues':parse_issues,'coverage_by_condition':coverage,
        'new_model_calls_by_readout':0,'expert_judgments_added':0,
        'scientific_accuracy_established':False,'scoring_rules_changed':False,
        'actual_command':[sys.executable,*sys.argv]}
    dest.mkdir(parents=True)
    save(dest/'observations.json',observations)
    save(dest/'paired_results.json',contrasts)
    save(dest/'metric_evidence_packets.json',packets)
    save(dest/'record_diagnostics.json',diagnostics)
    save(dest/'primary_replay.json',replays)
    save(dest/'provider_runtime.json',runtime)
    save(dest/'summary.json',summary)
    lines=['Source-bound direct-score evidence; author review, not expert gold.','']
    for p in packets:
        lines += [p['observation_id']+' / '+p['metric']+' / '+str(p['raw_score']),
            p['reasoning'], 'Evidence r: '+p['score_evidence']['r'],'']
    (dest/'REASONS.txt').write_text('\n'.join(lines),encoding='utf-8')
    save(dest/'verification.json',{'status':'pass' if all(c['passed'] for c in CHECKS) else 'completed_with_source_issues','checks':len(CHECKS),'check_details':CHECKS,
        'scope':'Frozen identity, original SR/SP, arithmetic, v7 replay, literal source binding; not scientific accuracy.',
        'authorization':bind(out/'additional_authorization.json'),
        'input_bindings':list(BINDINGS.values()),'code':bind(__file__),
        'outputs':[bind(p) for p in sorted(dest.iterdir()) if p.is_file()]})
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--dest',type=Path,required=True)
    main(parser.parse_args())
