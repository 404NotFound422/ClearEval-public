"""Two added r2 slots beside the frozen ten-slot public Codex assessment batch.

Never spawns or evaluates an agent. Original nine pending slots still use v3.
ROOT supplies the additive operational clock before reserve. No source/rubric,
schema, original converter, numerical function, or frozen v3 file is changed.
"""
from __future__ import annotations
import argparse, copy, sys
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_round2_subagent_judge_v3 as old
j, budget = old.j, old.budget
OUT = budget.OUT / 'codex_repeat_extension_v1'
VERSION = 'codex-two-additional-public-repeats-v1'
IDS = ['A01__codex_unobserved__r2', 'A02__codex_unobserved__r2']
REUSED = 'A01__codex_unobserved__r0'


def prepare(out):
    old.require(not out.exists(), 'NEW_EXTENSION_ONLY')
    plan, cases, matrix = old.root_gate(old.OUT, old.OUT / 'root_approval.json')
    counts = budget.counts()
    old.require(counts['phase']['E4'] == 19 and budget.LIMITS['E4'] == 30, 'EXPECTED_E4_19_WITH_11_REMAINING')
    row = old.selected(matrix, REUSED)
    terminal = old.directory(old.OUT, row) / 'terminal.json'
    result = j.read(terminal)
    old.require(result['status'] == 'success' and result['identity'] == row['identity'], 'EXACT_OLD_A01_SUCCESS')
    old.base.verify_bindings(result['bound_artifacts'])
    old.checked_receipt(old.OUT, row)
    old.require(j.filehash(row['submission_path']) == result['raw_sha256'], 'OLD_SUBMISSION_BYTES_CHANGED')
    for item in matrix:
        if item['cell_id'] != REUSED:
            old.require(not old.directory(old.OUT, item).exists(), 'OLD_PENDING_SLOT_ALREADY_STARTED')
    out.mkdir(parents=True)
    extras = []
    for aid in ['A01', 'A02']:
        source = old.selected(matrix, aid + '__codex_unobserved__r1')
        item = copy.deepcopy(source)
        item['cell_id'] = aid + '__codex_unobserved__r2'
        item['repeat_index'] = 2
        item['submission_path'] = str(old.submission_path(out, item['cell_id']))
        packet = j.read(source['packet']['path'])
        packet['submission_path'] = item['submission_path']
        packet_path = out / 'packets' / (item['cell_id'] + '.json')
        old.once(packet_path, packet)
        item['packet'] = old.bind(packet_path)
        item['packet_bytes'] = packet_path.stat().st_size
        item['identity'].update(version=VERSION, repeat_index=2,
            submission_path=item['submission_path'], packet_sha256=item['packet']['sha256'])
        item['trial_id'] = j.digest(item['identity'])
        extras.append(item)
    old.once(out / 'extra_matrix.json', extras)
    combined = [dict(row, entrypoint=str(Path(old.__file__)), source_out=str(old.OUT),
        disposition='reuse_original_success' if row['cell_id'] == REUSED else 'one_new_fresh_assessment') for row in matrix]
    combined += [dict(row, entrypoint=str(Path(__file__)), source_out=str(out), disposition='one_new_fresh_assessment') for row in extras]
    old.once(out / 'matrix.json', combined)
    bound = [Path(__file__), old.OUT / 'plan.json', old.OUT / 'matrix.json', old.OUT / 'root_approval.json',
        terminal, Path(row['submission_path']), out / 'extra_matrix.json', out / 'matrix.json']
    bound += [Path(item['packet']['path']) for item in extras]
    old.once(out / 'plan.json', {'status':'fixed_before_new_dispatch', 'version':VERSION,
        'planned_observations':12, 'original_success_reused':1, 'planned_new_assessments':11,
        'repeat_counts':{'A01':3,'A02':3,'A03':2,'A04':2,'A05':2}, 'max_attempts':1,
        'fork_turns':'none', 'fixed_order':[item['cell_id'] for item in combined],
        'old_batch':old.bind(old.OUT / 'plan.json'), 'old_frozen_inputs':plan['frozen_inputs'],
        'frozen_inputs':[old.bind(p) for p in bound], 'evaluator':old.MODEL,
        'runtime_settings_observed':False, 'known_independent_family':False,
        'same_scientific_prompt_and_schema':True, 'same_provider_contract':False,
        'old_A01_raw_sha256':result['raw_sha256'], 'old_terminal_preserved':True,
        'old_v11_import_then_separate_uniform_fieldwise_reprocessing':True,
        'budget_snapshot':{k:v for k,v in counts.items() if k!='requests'},
        'time_authorization':'ROOT installs the newly authorized additive clock; original limits remain.',
        'new_assessments':0, 'actual_command':[sys.executable,*sys.argv]})
    messages=[]
    for item in combined:
        if item['disposition']=='reuse_original_success': continue
        messages.append({'cell_id':item['cell_id'], 'fork_turns':'none',
            'packet':item['packet'], 'submission_path':item['submission_path'],
            'message':'Read exactly this packet file once: '+item['packet']['path']+
                '. Follow its instructions. Do not read any other file or browse. Create the assigned submission file with apply_patch exactly once; do not revise or read it back. Return only an acknowledgement with the self-reported creation tool, number of writes, and whether revised.'})
    old.once(out / 'dispatch_messages.json', messages)
    validate(out)
    print(j.canonical({'status':'prepared_without_assessment','observations':12,'new_assessments_planned':11,'new_assessments':0}))


def validate(out):
    _, cases, original = old.root_gate(old.OUT, old.OUT / 'root_approval.json')
    plan = j.read(out / 'plan.json')
    old.require(plan['version']==VERSION and plan['planned_observations']==12 and plan['planned_new_assessments']==11, 'EXTENSION_SCOPE')
    old.base.verify_bindings(plan['frozen_inputs'])
    extras = j.read(out / 'extra_matrix.json')
    old.require([r['cell_id'] for r in extras]==IDS, 'EXACT_TWO_ADDED_SLOTS')
    for item in extras:
        source=old.selected(original,item['anonymous_answer_id']+'__codex_unobserved__r1')
        expected=copy.deepcopy(source)
        expected.update(cell_id=item['anonymous_answer_id']+'__codex_unobserved__r2',repeat_index=2,
            submission_path=str(old.submission_path(out,item['cell_id'])),packet=old.bind(out/'packets'/(item['cell_id']+'.json')))
        expected['packet_bytes']=Path(expected['packet']['path']).stat().st_size
        expected['identity'].update(version=VERSION,repeat_index=2,submission_path=expected['submission_path'],packet_sha256=expected['packet']['sha256'])
        expected['trial_id']=j.digest(expected['identity'])
        old.require(item==expected,'ONLY_REPEAT_AND_DELIVERY_METADATA_MAY_CHANGE')
        original_packet=j.read(source['packet']['path']);original_packet['submission_path']=item['submission_path']
        old.require(j.read(item['packet']['path'])==original_packet,'ORIGINAL_PROMPT_SCHEMA_EXACT')
        old.safe_submission(item['submission_path'],old.submission_path(out,item['cell_id']),out)
    return plan,cases,extras


def action(args):
    _,cases,matrix=validate(args.out);row=old.selected(matrix,args.cell_id);dest=old.directory(args.out,row)
    if args.action=='reserve':
        old.require(not dest.exists(),'CELL_ALREADY_RESERVED_NO_RETRY')
        sp=old.safe_submission(row['submission_path'],old.submission_path(args.out,row['cell_id']),args.out)
        old.require(not sp.exists(),'SUBMISSION_MUST_NOT_EXIST_BEFORE_RESERVATION')
        budget.guard('E4',1+old.remaining_qwen(),600)
        old.once(dest/'submission_precondition.json',{'cell_id':row['cell_id'],'submission_path':str(sp),'existed_before_reservation':False,'source_kind':old.SOURCE_KIND})
        receipt=budget.reserve('E4',row['trial_id'],old.MODEL,600)
        old.once(dest/'request_receipt.json',receipt)
        print(j.canonical({'status':'reserved_for_one_actual_spawn','cell_id':row['cell_id'],'packet':row['packet'],'submission_path':str(sp),'actual_agent_spawned':False}));return
    receipt=old.checked_receipt(args.out,row)
    old.require(not (dest/'terminal.json').exists(),'TERMINAL_NO_REPAIR_OR_RETRY')
    evidence=j.read(args.evidence)
    if args.action=='record-dispatch':
        identity=old.dispatch_evidence(evidence,row)
        existing=j.read(args.out/'matrix.json')
        for other in existing:
            p=Path(other['source_out'])/'observations'/other['cell_id']/'actual_dispatch_evidence.json'
            if p.exists():old.require(j.read(p)['actual_agent_id']!=evidence['actual_agent_id'],'FRESH_AGENT_PER_SLOT')
        old.once(dest/'actual_dispatch_evidence.json',args.evidence.read_bytes());old.once(dest/'observed_backend.json',identity)
        print(j.canonical({'status':'actual_dispatch_recorded','cell_id':row['cell_id']}));return
    dispatch=j.read(dest/'actual_dispatch_evidence.json');old.dispatch_evidence(dispatch,row)
    path=old.safe_submission(args.raw,Path(row['submission_path']),args.out);raw=path.read_bytes()
    old.submission_evidence(evidence,row,dispatch,raw)
    old.once(dest/'actual_return_evidence.json',args.evidence.read_bytes())
    case=next(c for c in cases if c['case_id']==row['case_id'])
    result=old.commit_score(dest,raw,case,j.read(row['source_document']['path']),row['step'])
    old.once(dest/'terminal.json',{**result,'cell_id':row['cell_id'],'trial_id':row['trial_id'],'identity':row['identity'],'attempt':1,
        'actual_agent_id':dispatch['actual_agent_id'],'actual_assessment_dispatched':True,'request_id':receipt['request_id'],
        'actual_return_evidence':old.bind(dest/'actual_return_evidence.json'),'bound_artifacts':[old.bind(p) for p in dest.iterdir() if p.is_file()]})
    print(j.canonical({'status':result['status'],'cell_id':row['cell_id'],'complete_numeric_CCE':result['complete_numeric_CCE']}))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prepare','verify','reserve','record-dispatch','import-result'])
    p.add_argument('--out',type=Path,default=OUT);p.add_argument('--cell-id');p.add_argument('--evidence',type=Path);p.add_argument('--raw',type=Path)
    a=p.parse_args();a.out=a.out.resolve()
    if a.action=='prepare':prepare(a.out)
    elif a.action=='verify':validate(a.out);print(j.canonical({'status':'exact_source_bindings_pass','new_assessments':0}))
    else:action(a)
if __name__=='__main__':main()
