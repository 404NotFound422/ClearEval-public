"""Read-only structural replay; no scoring, model calls, or scientific repair."""
from pathlib import Path
import ast
import asyncio
import contextlib
import copy
import hashlib
import io
import json
import socket
import sys
import time
from types import SimpleNamespace
from collections import Counter
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
sys.dont_write_bytecode = True
BASE = ROOT / 'artifacts/cce_validation'
OUT = BASE / 'diagnostics/root_cause_v1/extraction'
from evaluator_integrity import parse_judge_object, validate_legacy_extraction, validate_score_proposals
from models.Ollama_LLM import OllamaLLM


def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(v): return hashlib.sha256(json.dumps(v, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
def save(p, x): Path(p).write_text(json.dumps(x, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
def no_network(*a, **kw): raise RuntimeError('Offline diagnostic: network disabled')


class Pairs(list):
    """Keep repeated raw keys instead of collapsing them into a dictionary."""


def duplicate_metadata(node, path=()):
    found = []
    if isinstance(node, Pairs):
        groups = {}
        for key, value in node: groups.setdefault(key, []).append(value)
        for key, values in groups.items():
            if len(values) > 1:
                found.append({'parent_path': list(path), 'key_sha256': digest(key),
                    'occurrences': len(values), 'distinct_value_hashes': len({digest(v) for v in values}),
                    'value_types': [type(v).__name__ for v in values], 'scientific_values_emitted': False})
        for key, value in node:
            component = key if key in {'extraction','marker_dict','scores','completeness','correctness'} else 'key#'+digest(key)[:12]
            found.extend(duplicate_metadata(value, (*path, component)))
    elif isinstance(node, list):
        for i, value in enumerate(node): found.extend(duplicate_metadata(value, (*path, i)))
    return found


def actual_loader_and_wrapper():
    source = ROOT / 'OEQ_run_grading_new.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    evaluate = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'evaluate_response_with_teacher')
    outer = next(n for n in ast.walk(evaluate) if isinstance(n,ast.Try) and any(
        isinstance(s,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='scores_block' for t in s.targets) for s in n.body))
    start = next(i for i,n in enumerate(outer.body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='scores_block' for t in n.targets))
    end = next(i for i,n in enumerate(outer.body[start:],start) if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) and n.value.func.id=='validate_score_proposals')
    body = copy.deepcopy(outer.body[start:end+1])
    fn = ast.parse('def actual_loader(llm_output):\n    pass').body[0]
    fn.body = body
    helpers = [copy.deepcopy(n) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in {'get_model_response','_provider_generation_failed'}]
    ns = {'validate_teacher_extraction':validate_legacy_extraction,'validate_score_proposals':validate_score_proposals,
          'asyncio':asyncio,'datetime':datetime,'timezone':timezone}
    module = ast.fix_missing_locations(ast.Module(body=[fn,*helpers],type_ignores=[]))
    exec(compile(module,str(source),'exec'),ns)
    return ns['actual_loader'], ns['get_model_response'], {
        'source':str(source),'sha256':sha(source),'loader_first_line':outer.body[start].lineno,
        'loader_last_line':outer.body[end].end_lineno,'extracted_ast_sha256':digest(ast.dump(module)),
        'executed_original_AST_without_source_edits':True,'EGES_function_called':False}


def category(error):
    message = str(error)
    if 'Duplicate JSON key:' in message: return 'conflicting_or_repeated_JSON_key'
    if 'Missing teacher score:' in message: return 'missing_score_record'
    if 'missing required fields' in message: return 'missing_extraction_fields'
    return type(error).__name__


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    socket.create_connection = no_network; socket.socket.connect = no_network
    ledger = BASE / 'judges/request_ledger.jsonl'
    protected = {str(ledger):sha(ledger)}
    previous = read(BASE/'report_verification_references_v7.json')
    for k in ['input_sha256','output_sha256']:
        protected.update({str(BASE/p):h for p,h in previous[k].items()})
    for p in ['OEQ_run_grading_new.py','evaluator_integrity.py','models/Ollama_LLM.py','scripts/cce_validation.py','prompts/eval_oeq_teacher_rubric.txt']:
        protected[str(ROOT/p)] = sha(ROOT/p)
    for p,h in protected.items(): assert sha(p)==h,p
    loader, wrapper, ast_provenance = actual_loader_and_wrapper()
    plan = read(BASE/'judges/schema_decode_followup_v1/plan.json')
    dev_ids = {r['case_id']:r['anonymous_answer_id'] for r in plan['matrix'] if r['stage']=='development'}
    areas = {
        'original_holdout': BASE/'judges/local_extraction_holdout_v1/sealed/run',
        'prompt_v2_holdout': BASE/'judges/holdout_remediation_v2/sealed/run',
        'schema_development': BASE/'judges/schema_decode_followup_v1/development/sealed/run'}
    inputs = {}; rows = []; duplicate_providers = []
    contradictory_text = 'Do NOT put keys like C_step, Co_order, or marker_dict at the top level.'
    for stage,area in areas.items():
        paths = sorted((area/'trials').glob('*.json'))
        assert len(paths) == (5 if stage=='schema_development' else 15)
        for path in paths:
            trial=read(path); identity=trial['identity']; cid=identity['case_id']
            aid = dev_ids[cid] if stage=='schema_development' else cid.split('__')[0]
            attempt = area/'attempts'/f"{trial['trial_id']}_{trial['attempt']}"
            provider_path=attempt/'provider_response.json'; provider=read(provider_path)
            prompt_path=attempt/'prompt.txt'; prompt=prompt_path.read_text(encoding='utf-8')
            receipt=read(attempt/'request_receipt.json')
            for p in [path,provider_path,prompt_path,attempt/'request_receipt.json']:
                inputs[str(p)] = sha(p)
            raw=provider['response']; pairs=json.loads(raw,object_pairs_hook=Pairs)
            duplicates=duplicate_metadata(pairs)
            failure=None; strict_pass=False
            try:
                obj=parse_judge_object(raw); strict_pass=True
                loader(obj)
            except ValueError as e: failure=category(e)
            passed=failure is None
            assert passed == (trial['status']=='success'),(stage,aid)
            rows.append({'stage':stage,'answer_id':aid,'request_index':receipt['package_request_index'],
                'original_status':trial['status'],'replayed_original_loader_pass':passed,
                'strict_parse_pass':strict_pass,'first_gate_failure':failure,
                'provider_done':provider.get('done'),'provider_finish_reason':provider.get('done_reason'),
                'completion_tokens':provider.get('eval_count'),'output_cap':8192,
                'syntactically_complete_JSON':True,'duplicate_groups':duplicates,
                'mixed_case_format_instruction_present':contradictory_text in prompt,
                'provider_path':str(provider_path),'provider_sha256':sha(provider_path),
                'prompt_sha256':sha(prompt_path),'scientific_values_emitted':False})
            if duplicates: duplicate_providers.append((stage,aid,provider,provider_path))

    # Minimal fixtures execute the original loader's exact AST, with no biology.
    scores={'completeness':{k:{'score':0} for k in ['c_step','c_param']},
            'correctness':{k:{'score':0} for k in ['co_order','co_method','co_param','co_chem']}}
    extraction={'method_name':None,'marker_dict':{},'clearing_total_time_hours':None}
    canonical={'scores':scores,'extraction':extraction}
    flat={**extraction,**{k[0].upper()+k[1:]:v for group in scores.values() for k,v in group.items()}}
    mixed={'scores':{g:{k[0].upper()+k[1:]:v for k,v in block.items()} for g,block in scores.items()},'extraction':extraction}
    fixtures=[]
    for name,payload,expected in [('canonical_nested_lowercase',canonical,True),('legacy_flat_uppercase',flat,True),
                                  ('mixed_nested_uppercase',mixed,False),('missing_extraction',{'scores':scores},False)]:
        failure=None
        try: loader(payload)
        except ValueError as e: failure=str(e)
        assert (failure is None)==expected
        fixtures.append({'case':name,'accepted':failure is None,'observed_error':failure,'synthetic_only':True})
    synthetic='{"marker_dict":{"SYNTHETIC_MARKER":"SYNTHETIC_TARGET_A","SYNTHETIC_MARKER":"SYNTHETIC_TARGET_B"}}'
    ordinary=json.loads(synthetic)
    try: parse_judge_object(synthetic)
    except ValueError as e: strict_error=str(e)
    else: raise AssertionError('duplicate fixture unexpectedly accepted')
    fixtures.append({'case':'duplicate_name_information_loss','synthetic_only':True,
        'raw_pair_count':len(json.loads(synthetic,object_pairs_hook=Pairs)[0][1]),
        'ordinary_dict_entries':len(ordinary['marker_dict']),
        'ordinary_dict_retains':'SYNTHETIC_TARGET_B','strict_error':strict_error,
        'marker_schema_string_value_clause_passes_after_loss':all(isinstance(v,str) for v in ordinary['marker_dict'].values()),
        'not_a_full_JSON_schema_validator_test':True})

    # Replay original adapter and wrapper with saved provider replies, never a request.
    adapter_replays=[]
    for stage,aid,provider,provider_path in duplicate_providers:
        class SavedProvider:
            calls=0
            def generate(self,**kwargs): self.calls+=1; return provider
        local=OllamaLLM.__new__(OllamaLLM)
        local.client=SavedProvider(); local.max_length=8192; local.temperature=0.0
        local.model_name='offline_saved_response'; local.format='json'; local.enable_thinking=False; local.transport='offline_replay'
        class AsyncReplay:
            async def _acall(self,prompt): return local._generate(prompt)
        # This saved-return coroutine has no I/O suspension. Supply only the
        # wrapper's monotonic-clock dependency, avoiding Windows loop sockets.
        wrapper.__globals__['asyncio']=SimpleNamespace(get_running_loop=lambda:SimpleNamespace(time=time.monotonic))
        with contextlib.redirect_stdout(io.StringIO()):
            coro=wrapper(AsyncReplay(),'OFFLINE REPLAY: no model request',return_data=True,validate_protocol=False)
            try: coro.send(None)
            except StopIteration as done: result=done.value
            else: raise AssertionError('Saved-return replay unexpectedly suspended')
        assert result['failure_code']=='PROVIDER_EXCEPTION' and result['error_type']=='JudgeFormatError'
        assert provider['done'] is True and provider['done_reason']=='stop'
        adapter_replays.append({'stage':stage,'answer_id':aid,'saved_provider_sha256':sha(provider_path),
            'provider_done':True,'provider_finish_reason':'stop','original_adapter_error_type':result['error_type'],
            'original_wrapper_failure_code':result['failure_code'],'original_wrapper_metadata_retained':bool(result['metadata']),
            'replayed_provider_stub_calls':local.client.calls,'real_provider_calls':0,
            'wrapper_clock_dependency':'offline monotonic clock; coroutine driven without an event-loop socket',
            'interpretation':'Completed provider text fails inside adapter parsing; wrapper classifies that exception as PROVIDER_EXCEPTION before runner labels TEACHER_GENERATION.'})

    stage_summary=[]
    for stage in areas:
        subset=[r for r in rows if r['stage']==stage]
        stage_summary.append({'stage':stage,'attempted':len(subset),'pass':sum(r['replayed_original_loader_pass'] for r in subset),
            'failures':dict(Counter(r['first_gate_failure'] for r in subset if r['first_gate_failure'])),
            'all_provider_done_stop':all(r['provider_done'] and r['provider_finish_reason']=='stop' for r in subset),
            'mixed_case_instruction_count':sum(r['mixed_case_format_instruction_present'] for r in subset)})
    assert [s['pass'] for s in stage_summary]==[7,14,4]
    for p,h in {**protected,**inputs}.items(): assert sha(p)==h,p
    summary={'status':'pass','scope':'offline structural diagnosis; no biological rescoring, repair or scientific field disclosure',
        'stages':stage_summary,'original_gate_replays':len(rows),'duplicate_adapter_replays':len(adapter_replays),
        'original_contract_AST':ast_provenance,'synthetic_fixtures':fixtures,'adapter_replays':adapter_replays,
        'important_new_source_fact':'The format enforcement wrapper itself names uppercase C_step/Co_order and asks to nest them, while the nested validator requires lowercase. All35 actually submitted prompts retain this mixed instruction.',
        'causal_limits':['The prompt discrepancy and loader rejection are directly reproduced; model psychological causation is not proven.',
            'Original to v2 changes a combined set of schema/example prompt elements. 7->14 does not isolate a single text edit.',
            'Duplicate-key generation under the tested schema is observed; its model/backend internal cause has not been isolated.',
            'A format pass or identity replay does not establish scientific faithfulness.'],
        'new_model_requests':0,'new_scientific_scores':0,'original_files_unchanged':True,
        'diagnostic_implementation_attempts':[{'attempt':1,'exit_code':1,'error':'StopIteration in diagnostic AST locator; no original code or data changed'},
            {'attempt':2,'exit_code':1,'error':'Offline socket guard also blocked the Windows event-loop self-pipe; no provider call'},
            {'attempt':3,'exit_code':0,'change':'Locate original AST by assignment and drive saved-return coroutine with only its clock dependency substituted'}],
        'input_sha256':inputs,'protected_sha256':protected,'script_sha256':sha(__file__),
        'actual_command':[sys.executable,'scripts/cce_diagnose_extraction_v1.py'],'python_version':sys.version}
    save(OUT/'per_return_trace.json',rows); save(OUT/'trace.json',summary)
    save(OUT/'software_fixtures.json',{'scope':'synthetic implementation probes only, not expert labels or experiment answers','records':fixtures})
    print(json.dumps({'status':'pass','original_gate_replays':len(rows),'passes':[s['pass'] for s in stage_summary],
        'real_duplicate_adapter_replays':len(adapter_replays),'synthetic_fixtures':len(fixtures),'new_model_requests':0}))


if __name__=='__main__': main()
