"""Exact-token capacity adapter for the already frozen round-3 confirmation batch.

This is a mechanical capacity-gate correction. Original runner code, batch files,
scientific inputs, scoring, budget accounting and processing fingerprint stay fixed.
Only an explicit `run --allow-local-calls` invokes the original generator.
"""
from __future__ import annotations
import argparse, asyncio, copy, datetime, hashlib, json, sys, urllib.request
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
R3 = ROOT / 'artifacts/cce_validation/optimizer_round3_20261011'
AUDIT = R3 / 'problem_cycles/context_capacity_cycle01'
BATCH = R3 / 'confirmation_qwen_01'
CERTIFICATE = AUDIT / 'capacity_certificate.json'
FREEZE = AUDIT / 'adapter_freeze.json'
RUNNER_PATH = ROOT / 'scripts/cce_round3_runner_v2.py'
RUNNER_SHA256 = '45a4c5e5543e6c527da4efd0946a0721ecca5c78e34126529a1df81cf7c11544'
CERTIFICATE_SHA256 = '815d6165edac1c67a639880db964640f311dc4c6cf859b3b81335ee6f4b4cc06'

def require(ok, label):
    if not ok: raise ValueError(label)
def ordered(x): return json.dumps(x, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf8')
def digest(x): return hashlib.sha256(x).hexdigest()
def read(p): return json.loads(Path(p).read_bytes())
def bind(p): return {'path':str(Path(p).resolve()), 'sha256':digest(Path(p).read_bytes())}
def check(b): require(bind(b['path'])['sha256'] == b['sha256'], 'BOUND_FILE_CHANGED:' + b['path'])
def save_once(p, x):
    p=Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('xb') as f: f.write(ordered(x) + b'\n')
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def original_runner():
    require(bind(RUNNER_PATH)['sha256'] == RUNNER_SHA256, 'FROZEN_RUNNER_CHANGED')
    import cce_round3_runner_v2 as runner
    return runner

def certificate():
    require(bind(CERTIFICATE)['sha256'] == CERTIFICATE_SHA256, 'CERTIFICATE_CHANGED')
    c=read(CERTIFICATE)
    require(c['schema']=='cce_exact_runtime_capacity_certificate_v1' and c['status']=='verified', 'CERTIFICATE_STATUS')
    require(c['new_inference_requests']==0 and c['control_count']==8 and c['all_control_count_and_token_prefix_matches'] is True, 'CERTIFICATE_CONTROLS')
    require(Path(c['batch_out']).resolve()==BATCH.resolve(), 'CERTIFICATE_BATCH')
    for b in [c['plan'],c['matrix'],c['runner'],c['confirmation_configuration_freeze'],*c['evidence_bindings']]: check(b)
    require(c['runner']==bind(RUNNER_PATH), 'CERTIFICATE_RUNNER')
    require(c['tokenize_options']=={'add_special':True,'parse_special':True}, 'TOKENIZE_OPTIONS')
    require(c['default_system']=='' and c['default_model_messages']==[], 'DEFAULT_SYSTEM_OR_MESSAGES')
    require((c['context_length'],c['maximum_output_tokens'],c['safety_margin_tokens'])==(98304,8192,256), 'CERTIFICATE_BUDGET')
    return c

def adapt_rows(plan, matrix, cert):
    """Return isolated row copies after full per-payload/token-evidence validation."""
    require(plan['public_model']==cert['public_model'], 'PUBLIC_MODEL_CHANGED')
    require(plan['processing_fingerprint']==cert['processing_fingerprint'], 'PROCESSING_FINGERPRINT_CHANGED')
    require(plan['phase']=='confirmation' and plan['case_count']==8 and plan['planned_observations']==8 and plan['repeats']==1 and plan['max_attempts']==1, 'CONFIRMATION_SCOPE')
    require(len(matrix)==len(cert['cells'])==8, 'CERTIFICATE_COVERAGE')
    require([r['planned_trial_id'] for r in matrix]==[c['trial_id'] for c in cert['cells']], 'TRIAL_ORDER_OR_ID_CHANGED')
    require(len({r['planned_trial_id'] for r in matrix})==8, 'DUPLICATE_TRIAL')
    adapted=copy.deepcopy(matrix); changes=[]
    for original, row, cell in zip(matrix, adapted, cert['cells']):
        require((row['case_id'],row['anonymous_answer_id'])==(cell['case_id'],cell['anonymous_answer_id']), 'CELL_IDENTITY')
        for key in ['payload','prompt','schema']:
            require(row['assets'][key]==cell[key], 'CELL_ASSET_BINDING')
            check(cell[key])
        payload=read(cell['payload']['path']); prompt=Path(cell['prompt']['path']).read_bytes()
        require(payload['prompt'].encode('utf8')==prompt, 'FULL_PROMPT_BYTES')
        require(digest(ordered(payload))==row['ordered_payload_sha256']==cell['ordered_payload_sha256'], 'ORDERED_PAYLOAD_CHANGED')
        require(payload['format']==read(cell['schema']['path']), 'FULL_SCHEMA_CHANGED')
        require(set(payload)=={'model','prompt','format','stream','options','think'}, 'PAYLOAD_KEYS')
        require(payload['model']==cert['public_model']['model'] and payload['think'] is False and payload['stream'] is False, 'MODEL_THINK_STREAM_CHANGED')
        require(payload['options']=={'num_ctx':98304,'num_predict':8192,'temperature':0.0}, 'GENERATION_OPTIONS_CHANGED')
        require(row['fits_context'] is cell['original_fits_context'] and row['context_bound']==cell['original_byte_bound'], 'ORIGINAL_GATE_CHANGED')
        require(row['context_bound']==len(prompt)+8192+256, 'ORIGINAL_BYTE_BOUND')
        for key in ['template_request','template_response','tokenize_request','token_ids_response']: check(cell[key])
        template_request=read(cell['template_request']['path'])
        require(template_request['messages']==[{'role':'user','content':payload['prompt']}], 'TEMPLATE_FULL_USER_CONTENT')
        require(template_request['chat_template_kwargs']=={'enable_thinking':False}, 'TEMPLATE_THINK')
        require(template_request['response_format']=={'type':'json_schema','json_schema':{'name':'schema','schema':payload['format']}}, 'TEMPLATE_FULL_SCHEMA')
        rendered=read(cell['template_response']['path'])['prompt']
        prefix='<|im_start|>user\n'; suffix='<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'
        require(rendered==prefix+payload['prompt'].strip()+suffix, 'NATIVE_CONTENT_LOSS_OR_CHANGED_TEMPLATE')
        require(digest(rendered.encode('utf8'))==cell['native_prompt_sha256'], 'NATIVE_PROMPT_HASH')
        require(read(cell['tokenize_request']['path'])=={'content':rendered,'add_special':True,'parse_special':True}, 'EXACT_TOKENIZE_REQUEST')
        tokens=read(cell['token_ids_response']['path'])['tokens']
        require(all(type(t) is int for t in tokens), 'TOKEN_ID_TYPE')
        require(len(tokens)==cell['exact_input_tokens_including_special'] and digest(ordered(tokens))==cell['token_ids_sha256'], 'EXACT_TOKEN_SEQUENCE')
        require(cell['reserved_output_tokens']==8192 and cell['retained_safety_margin_tokens']==256 and cell['configured_context']==98304, 'CELL_RESERVES')
        total=len(tokens)+8192+256
        require(type(cell['exact_total_with_reserves']) is int and total==cell['exact_total_with_reserves'] and cell['capacity_margin_tokens']==98304-total, 'CELL_CAPACITY_ARITHMETIC')
        require(cell['exact_fits_context'] is True and total<=98304, 'EXACT_CONTEXT_LIMIT')
        if not row['fits_context']:
            changes.append({'trial_id':row['planned_trial_id'],'from_fits_context':False,'to_fits_context':True})
            row['fits_context']=True
        untouched=copy.deepcopy(row); untouched['fits_context']=original['fits_context']
        require(untouched==original, 'NON_GATE_MUTATION')
    require(changes==cert['allowed_gate_changes'] and len(changes)==1, 'UNAUTHORIZED_GATE_CHANGES')
    require(changes[0]['trial_id']==next(r['planned_trial_id'] for r in matrix if r['anonymous_answer_id']=='R3C02'), 'ONLY_R3C02_ALLOWED')
    return adapted, changes

def runtime_identity(cert, port):
    require(type(port) is int and 1<=port<=65535, 'RUNNER_PORT')
    # Read-only local metadata endpoint, no generation or tokenization request.
    request=urllib.request.Request(f'http://127.0.0.1:{port}/props', method='GET')
    with urllib.request.urlopen(request,timeout=10) as response: props=json.load(response)
    ident=cert['runtime_identity']; weight=ident['full_weight_file_hash']
    require(Path(props['model_path']).resolve()==Path(weight['path']).resolve(), 'LOADED_WEIGHT_PATH')
    require(Path(weight['path']).stat().st_size==weight['bytes'], 'WEIGHT_FILE_SIZE')
    check(ident['manifest'])
    require(ident['manifest']['sha256']==cert['public_model']['model_digest'], 'MANIFEST_MODEL_IDENTITY')
    require(props['build_info']==ident['runner_build_info'], 'TOKENIZER_BUILD_IDENTITY')
    require(props['default_generation_settings']['n_ctx']==cert['context_length'], 'RUNTIME_CONTEXT')
    require(digest(props['chat_template'].encode('utf8'))==ident['native_template_sha256'], 'RUNTIME_TEMPLATE')
    return {'endpoint':f'http://127.0.0.1:{port}/props','model_path':props['model_path'],
            'build_info':props['build_info'],'n_ctx':props['default_generation_settings']['n_ctx'],
            'native_template_sha256':ident['native_template_sha256'],'read_only_metadata':True}

def verify(out, port):
    require(Path(out).resolve()==BATCH.resolve(), 'EXACT_PREPARED_CONFIRMATION_BATCH_ONLY')
    runner=original_runner(); cert=certificate()
    # All original file, step, identity, scientific and actual model checks run first.
    plan,cases,matrix,contract=runner.validate(BATCH,query_service=True)
    adapted,changes=adapt_rows(plan,matrix,cert)
    runtime=runtime_identity(cert,port)
    report={'status':'pass','created_utc':now(),'capacity_only':True,'new_inference_requests':0,
            'certificate':bind(CERTIFICATE),'adapter':bind(__file__),'original_runner':bind(RUNNER_PATH),
            'original_plan':bind(BATCH/'plan.json'),'original_matrix':bind(BATCH/'matrix.json'),
            'full_payloads_verified':len(matrix),'exact_token_certificates_verified':len(cert['cells']),
            'only_in_memory_gate_changes':changes,'original_source_files_unchanged':True,
            'processing_fingerprint':plan['processing_fingerprint'],'runtime_identity':runtime,
            'original_matrix_digest':digest(ordered(matrix)),'adapted_matrix_digest':digest(ordered(adapted))}
    return report

def freeze(args):
    require(not (BATCH/'run').exists(), 'CONFIRMATION_ALREADY_STARTED_BEFORE_CAPACITY_FREEZE')
    report=verify(args.out,args.runner_port)
    value={'schema':'cce_capacity_adapter_freeze_v1','created_utc':now(),
           'revision_type':'mechanical capacity criterion correction before confirmation inference',
           'adapter':bind(__file__),'certificate':bind(CERTIFICATE),'runner':bind(RUNNER_PATH),
           'plan':bind(BATCH/'plan.json'),'matrix':bind(BATCH/'matrix.json'),
           'confirmation_configuration_freeze':bind(R3/'confirmation_configuration_freeze.json'),
           'processing_fingerprint':report['processing_fingerprint'],'verification':report,
           'original_frozen_files_mutated':False,'all_scientific_settings_unchanged':True,
           'original_num_ctx':98304,'original_output_budget':8192,'original_margin':256,
           'new_model_requests_during_freeze':0,
           'scope':'same 8 confirmation cells; original runner budget, single attempt, payload and scoring',
           'root_start_condition':'ROOT starts only after E2 24 completion and independent review'}
    save_once(FREEZE,value)
    return {'status':'frozen','freeze':bind(FREEZE),'verification':report,'new_inference_requests':0}

def checked_freeze():
    f=read(FREEZE)
    require(f['schema']=='cce_capacity_adapter_freeze_v1' and f['original_frozen_files_mutated'] is False
            and f['all_scientific_settings_unchanged'] is True, 'ADAPTER_FREEZE_STATUS')
    for key in ['adapter','certificate','runner','plan','matrix','confirmation_configuration_freeze']: check(f[key])
    require(f['adapter']==bind(__file__) and f['certificate']==bind(CERTIFICATE), 'ADAPTER_FREEZE_IDENTITY')
    return f

def install_runtime_adapter(runner, cert):
    original=runner.validate
    def validate(out,query_service=False):
        p,c,m,k=original(out,query_service)
        if Path(out).resolve()==BATCH.resolve(): m,_=adapt_rows(p,m,cert)
        return p,c,m,k
    runner.validate=validate
    return original

def run(args):
    require(args.allow_local_calls,'EXPLICIT_ROOT_LOCAL_CALL_FLAG_REQUIRED')
    require(type(args.max_new_calls) is int and 0<=args.max_new_calls<=8,'CONFIRMATION_CALL_CAP')
    checked_freeze(); verify(args.out,args.runner_port)
    runner=original_runner(); cert=certificate()
    original=install_runtime_adapter(runner,cert)
    try:
        original_args=argparse.Namespace(out=BATCH,allow_local_calls=True,max_new_calls=args.max_new_calls,reuse_from=[])
        return asyncio.run(runner.run(original_args))
    finally: runner.validate=original

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['verify','freeze','run'])
    parser.add_argument('--out',type=Path,default=BATCH)
    parser.add_argument('--runner-port',type=int,required=True)
    parser.add_argument('--report',type=Path)
    parser.add_argument('--allow-local-calls',action='store_true')
    parser.add_argument('--max-new-calls',type=int,default=0)
    args=parser.parse_args()
    if args.action!='run': require(not args.allow_local_calls and args.max_new_calls==0,'NO_CALL_FLAGS_IN_DRY_RUN')
    result=verify(args.out,args.runner_port) if args.action=='verify' else freeze(args) if args.action=='freeze' else run(args)
    if args.report: save_once(args.report,result)
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))

if __name__=='__main__': main()
