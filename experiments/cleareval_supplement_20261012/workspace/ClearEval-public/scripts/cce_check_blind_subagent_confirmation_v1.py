"""Synthetic controller checks; no sealed reads, HTTP, ledger edits, or agents."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import socket
import sys
import tempfile
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'scripts')]
import cce_blind_subagent_confirmation_v1 as c

def main():
    checks=[]
    def check(name,value):
        if not value:raise AssertionError(name)
        checks.append({'name':name,'pass':True,'synthetic_or_design_only':True})
    def rejected(name,fn):
        try:fn()
        except (ValueError,TypeError,FileExistsError,UnicodeError):check(name,True)
        else:raise AssertionError(name+' was accepted')
    def no_network(*args,**kwargs):raise AssertionError('NETWORK_FORBIDDEN')
    socket.create_connection=no_network
    old_release=c.RELEASE;out_existed=c.OUT.exists();script_snapshot=c.bind(c.__file__)
    policy,matrix=c.design();check('fixed_8_by_2_not_families',len(matrix)==16 and policy['design']['distinct_model_families_claimed'] is False)
    check('all_attempt1_fork_none',all(x['attempt']==1 for x in matrix) and c.rules()['fork_turns']=='none')
    rejected('fenced_JSON_rejected',lambda:c.strict_json(b'```json\n{}\n```'))
    rejected('trailing_JSON_rejected',lambda:c.strict_json(b'{} {}'))
    rejected('duplicate_keys_rejected',lambda:c.strict_json(b'{"scores":{},"scores":{}}'))
    rejected('nested_duplicate_keys_rejected',lambda:c.strict_json(b'{"scores":{"x":0,"x":1}}'))
    rejected('NaN_rejected',lambda:c.strict_json(b'{"value":NaN}'))
    rejected('Infinity_rejected',lambda:c.strict_json(b'{"value":Infinity}'))
    rejected('overflow_number_rejected',lambda:c.strict_json(b'{"value":1e9999}'))
    rejected('array_top_level_rejected',lambda:c.strict_json(b'[]'))
    rejected('invalid_utf8_rejected',lambda:c.strict_json(b'\xff'))
    check('known_zero_and_null_retained',c.strict_json(b'{"x":0,"y":null}')=={'x':0,'y':None})
    record={'anonymous_answer_id':'C01','question_id':999,'specific_question':'Describe the two colored tokens.',
      'model_response':'Token A is blue.\nToken B is orange.','references':[{'reference_id':'toy-source','text':'Two colored tokens.'}]}
    check('sanitized_record_whitelist',set(c.clean_record(record))==c.SAFE_RECORD_KEYS-{'anonymous_answer_id'})
    rejected('generator_metadata_rejected',lambda:c.clean_record({**record,'generator_model':'synthetic-hidden'}))
    unsafe=copy.deepcopy(record);unsafe['references'][0]['human_confirmation']='not allowed'
    rejected('nested_reviewer_metadata_rejected',lambda:c.clean_record(unsafe))
    check('sealed_and_identity_paths_rejected',all(c.protected_path(p) for p in [r'X:\sealed_confirmation\x.json',r'X:\confirmation_manifest.json',r'X:\identity_key.json',r'X:\human_review\holdout.json']))
    class Toy:
        @staticmethod
        def source_id_for_case(case):return 'SRC_'+c.rawsha(case['specific_question']+'\0'+case['model_response'])[:24]
        @staticmethod
        def document(text,source_id):return {'source_id':source_id,'text':text,'units':[{'unit_id':'U1','text':text}]}
        @staticmethod
        def candidate_registry(doc):return {'source_id':doc['source_id'],'records':[]}
        @staticmethod
        def make_prompt(case,doc):return case['specific_question']+'\n'+case['model_response']+'\n'+c.canonical(case['references'])
    packet=c.packet(record,Toy,{'type':'object'})
    check('packet_preserves_exact_source',packet['source_document']['text']==record['model_response'] and record['model_response'] in packet['prompt'])
    check('packet_hides_cell_and_generator_meta','C01' not in packet['prompt'] and 'generator_model' not in packet['prompt'])
    check('same_answer_replicates_have_same_model_input',packet==c.packet(record,Toy,{'type':'object'}))
    primary=[{'event':'request_started'} for _ in range(284)]
    reserved=[{'event':'assessment_reserved','cell_id':x['cell_id']} for x in matrix]
    snap=c.budget_snapshot(primary,reserved)
    check('all16_reservations_fill300',snap['combined_reserved_or_used']==300 and snap['external_actual_dispatched']==0)
    rejected('301_combined_rejected',lambda:c.budget_snapshot(primary+[{'event':'request_started'}],reserved))
    rejected('duplicate_reservation_rejected',lambda:c.budget_snapshot(primary,reserved+[reserved[0]]))
    rejected('dispatch_without_reservation_rejected',lambda:c.budget_snapshot([],[{'event':'assessment_dispatched','cell_id':'C01_codex_review_1'}]))
    dispatched=[{'event':'assessment_dispatched','cell_id':x['cell_id']} for x in matrix]
    check('actual_dispatch_count_distinct_from_reserve',c.budget_snapshot(primary,reserved+dispatched)['combined_actual_requests_or_assessments']==300)
    rejected('duplicate_actual_dispatch_rejected',lambda:c.budget_snapshot(primary,reserved+dispatched+[dispatched[0]]))
    statuses=c.status_rows(matrix,[]);check('all16_missing_retained',len(statuses)==16 and all(x['status']=='not_released' for x in statuses))
    events=[reserved[0],dispatched[0],{'event':'assessment_terminal','cell_id':matrix[0]['cell_id'],'status':'failed'}]
    check('failed_and_other15_retained',c.status_rows(matrix,events)[0]['status']=='failed' and len(c.status_rows(matrix,events))==16)
    cell={**matrix[0],'prompt_sha256':'toy-hash'}
    evidence={'recorded_by':'root_agent','event':'actual_subagent_started','tool_name':'collaboration.spawn_agent','fork_turns':'none',
      'cell_id':cell['cell_id'],'prompt_sha256':'toy-hash','actual_agent_id':'SYNTHETIC_ONLY_NOT_SPAWNED','one_packet_only':True,
      'followup_sent':False,'actual_tool_receipt':{'synthetic_only':True},'declared_model_override':'unverified-model'}
    check('model_override_does_not_prove_backend',c.validate_dispatch(evidence,cell)['backend_identity']=='unknown')
    rejected('fork_all_rejected',lambda:c.validate_dispatch({**evidence,'fork_turns':'all'},cell))
    rejected('followup_rejected',lambda:c.validate_dispatch({**evidence,'followup_sent':True},cell))
    rejected('mismatched_packet_rejected',lambda:c.validate_dispatch({**evidence,'prompt_sha256':'wrong'},cell))
    with tempfile.TemporaryDirectory(prefix='blind_synthetic_',dir=c.DRAFT) as temp:
        directory=Path(temp);c.RELEASE=directory/'missing_release.json'
        rejected('missing_release_blocks_before_source_read',c.gate)
        def convert(raw,doc):return {'raw_response_sha256':c.rawsha(raw),'raw_content_preserved':raw,'legacy_runner_payload':{'scores':json.loads(raw)['scores']}}
        raw=b'{"scores":{},"extra":"synthetic"}\r\n'
        success=c.commit_and_parse(directory/'valid',raw,convert,{})
        check('raw_bytes_preserved_including_CRLF',(directory/'valid/raw_response.txt').read_bytes()==raw)
        check('raw_sha_record_matches_before_parse',c.read(directory/'valid/raw_commit.json')['raw_sha256']==c.rawsha(raw) and success['status']=='success')
        rejected('raw_response_cannot_be_overwritten',lambda:c.commit_and_parse(directory/'valid',raw,convert,{}))
        fail=c.commit_and_parse(directory/'invalid',b'{not-json}',convert,{})
        check('invalid_raw_kept_with_failed_observation',fail['status']=='failed' and (directory/'invalid/raw_commit.json').exists() and (directory/'invalid/raw_response.txt').read_bytes()==b'{not-json}')
        def bad_conversion(raw,doc):raise ValueError('synthetic converter failure')
        failed=c.commit_and_parse(directory/'conversion_fail',raw,bad_conversion,{})
        check('conversion_failure_keeps_raw_no_fallback',failed['status']=='failed' and (directory/'conversion_fail/raw_commit.json').exists() and not (directory/'conversion_fail/conversion.json').exists())
        def modified(raw,doc):return {'raw_response_sha256':c.rawsha(raw),'raw_content_preserved':raw,'legacy_runner_payload':{'scores':{'changed':1}}}
        check('direct_score_change_rejected',c.commit_and_parse(directory/'score_change',raw,modified,{})['status']=='failed')
    c.RELEASE=old_release
    check('no_real_output_or_source_script_change',c.OUT.exists()==out_existed and c.bind(c.__file__)==script_snapshot)
    output={'status':'pass','scope':'software synthetic fixtures and public design metadata only','checks':checks,
      'actual_model_requests':0,'actual_external_assessments':0,'primary_ledger_reads_or_writes':0,
      'sealed_or_human_inputs_read':False,'real_release_or_packet_freeze_created':False,'real_packets_created':False,
      'script':script_snapshot,'checker':c.bind(__file__),'policy':c.bind(c.DESIGN/'policy.json'),'matrix':c.bind(c.DESIGN/'matrix.json'),
      'actual_command':[sys.executable,*sys.argv],'not_independent_HTTP_or_generation_review':True}
    c.write(c.DRAFT/'software_checks.json',output)
    print(c.canonical({'status':'pass','checks':len(checks),'actual_external_assessments':0,'real_primary_ledger_access':False}))

if __name__=='__main__':main()
