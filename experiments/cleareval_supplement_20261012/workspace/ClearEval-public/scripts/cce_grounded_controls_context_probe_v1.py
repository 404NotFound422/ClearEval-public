"""Generate 21 full prompts in memory only, measure bounds, make no requests."""
import contextlib
import argparse
import importlib
import io
from pathlib import Path
import socket
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_validation as core
import cce_output_contract_v1 as parent

def no_network(*args,**kwargs):raise RuntimeError('Context probe permits no network')

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--backend',choices=['v2','v3'],default='v3');options=parser.parse_args()
 grounded=importlib.import_module('cce_grounded_extraction_'+options.backend)
 # Windows asyncio uses a local socket pair for its own event loop. Blocking
 # socket.connect also blocks that non-model mechanism; block HTTP connectors
 # instead. exact_runner_prompt supplies an in-memory CaptureOnly teacher.
 socket.create_connection=no_network
 out=ROOT/'artifacts/cce_validation/optimizer_20261010/grounded_controls_design_v1'
 source=ROOT/'artifacts/cce_validation/judges/controls_contract_v2/cases.json'
 paths=[Path(__file__),Path(grounded.__file__),source]
 paths += [p for p in [grounded.OUT/'plan.json',grounded.OUT/'schema.json',grounded.OUT/'draft/schema.json',grounded.OUT/'draft/draft_manifest.json'] if p.exists()]
 bindings=[{'path':str(p),'sha256':core.filehash(p)} for p in paths]
 before=parent.request_count();cases=core.read(source)['cases'];rows=[]
 for c in cases:
  sid=grounded.source_id_for_case(c);doc=grounded.document(c['model_response'],sid)
  with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):prompt=grounded.make_prompt(c,doc)
  assert doc['text']==c['model_response'] and ''.join(u['text'] for u in doc['units'])==c['model_response']
  marker='[LOSSLESS INDEXED MODEL_PROTOCOL; concatenate text fields in order]\n'
  indexed=marker in prompt
  if indexed:
   units=[{'unit_id':u['unit_id'],'text':u['text']} for u in doc['units']]
   assert prompt.count(marker+grounded.canonical(units))==1
  else:assert c['model_response'] in prompt
  assert prompt.endswith(parent.v2.reference_suffix(c))
  for field in ['case_id','base_id','generator_model']:
   value=c.get(field)
   if value and value not in c['specific_question'] and value not in c['model_response']:assert value not in prompt
  bound=len(prompt.encode('utf8'))+8192+256
  rows.append({'case_id':c['case_id'],'question_id':c['question_id'],'condition':c['condition'],
    'source_id':sid,'answer_raw_sha256':grounded.rawsha(c['model_response']),
    'prompt_raw_sha256':grounded.rawsha(prompt),'prompt_characters':len(prompt),'prompt_utf8_bytes':len(prompt.encode('utf8')),
    'conservative_bound':bound,'configured_context':40960,'max_output_tokens':8192,'template_reserve':256,'fits_40960':bound<=40960,
    'case_id_absent_from_prompt':c['case_id'] not in prompt,'full_answer_and_reference_not_truncated':True,
    'lossless_indexed_source_used':indexed,'source_unit_count':len(doc['units']),
    'source_units_exactly_reconstruct_answer':True,'reference_suffix_unchanged':True})
 assert len(rows)==21
 assert bindings==[{'path':str(p),'sha256':core.filehash(p)} for p in paths],'draft_changed_during_context_probe'
 result={'status':'all_fit' if all(r['fits_40960'] for r in rows) else 'context_overflow_requires_review',
   'backend_version':options.backend,'candidate_stage':'current_draft_snapshot_not_final_selection',
   'actual_full_prompts_built_in_memory':21,'minimum_bound':min(r['conservative_bound'] for r in rows),
   'maximum_bound':max(r['conservative_bound'] for r in rows),'over_limit':sum(not r['fits_40960'] for r in rows),
   'inputs':bindings,'current_schema_canonical_sha256':grounded.rawsha(grounded.canonical(grounded.schema())),
   'matrix':rows,'actual_command':[sys.executable,*sys.argv],'new_model_requests':0,'experiment_freeze_performed':False,
   'prompt_files_written':False,'configuration_changed':False,'snapshot_not_final_E2_contract':True,
   'ledger_before':before,'ledger_after':parent.request_count(),'new_requests_by_this_probe':0,
   'ledger_note':'Any concurrent other-agent requests are not attributed to the in-memory prompt probe.'}
 core.write(out/('context_probe_'+options.backend+'_snapshot.json'),result)
 import json
 print(json.dumps({k:v for k,v in result.items() if k not in ['inputs','matrix']}))
 for r in rows:print(json.dumps({k:r[k] for k in ['question_id','condition','conservative_bound','fits_40960']}))

if __name__=='__main__':main()
