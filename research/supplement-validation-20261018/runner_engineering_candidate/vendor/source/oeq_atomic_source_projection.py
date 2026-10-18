"""Opt-in, closed-world Q13 atomic-source pilot, preserving the legacy default.

A mechanical source expansion is not promoted to a literal quote. DERIVED remains
DERIVED in evidence; only the exact source-anchored, hash-locked expansion below
is eligible. All other derived prose still uses the existing exclusion policy.
"""
from copy import deepcopy
import hashlib,importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
HOME=ROOT/'experiments/idisco_full_atomic_reference_20261015'
KEY='idisco-dec2016-atomic-clearing-v1'
VERSION='q13-atomic-clearing-admission-v1'
LOCK_SHA256='0f3f36a1284800cd42bac17742607d2c8d501492ddba8c52418a12e3046e7bf7'

def _read(p):return json.loads(p.read_text())
def _sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def _locked():
 p=HOME/'atomic_admission_lock_v1.json'
 if _sha(p)!=LOCK_SHA256:raise ValueError('Atomic admission registry lock changed')
 lock=_read(p)
 for name,digest in lock['files'].items():
  if _sha(HOME/name)!=digest:raise ValueError('Atomic admission frozen input changed: '+name)
 return lock

def check_source(question,assessment,evidence,key):
 from oeq_task_evidence import validate_selected_task_evidence
 if key!=KEY:raise ValueError('Unsupported atomic source key')
 lock=_locked();expected=_read(HOME/'requested_clearing_projection_v1.json')
 validate_selected_task_evidence(evidence)
 if evidence!=expected:raise ValueError('Atomic expansion differs from registered source-anchored projection')
 if question['question_id']!=13 or question['question']!=expected['question']:
  raise ValueError('Atomic pilot requires the frozen Q13 task; other tasks need explicit scope review')
 if assessment['method_identity'].get('status')!='SATISFIED' or assessment['method_identity'].get('branches')!={'main':['iDISCO+']}:
  raise ValueError('Atomic source method/route mismatch')
 # Check mechanical expansion anchors independently of caller-supplied readiness.
 card={c['id']:c for c in evidence['cards']}
 atomic=_read(HOME/'paired_requested_clearing_wash4.json')['reference']['operations']
 byid={r['id']:r for r in atomic}
 for row in evidence['sr_inventory']['reference_steps']:
  r=byid[row['reference_step_id']];x=row['atomic_expansion']
  if row['text_origin']!='DERIVED' or row['text']!=r['raw_text']:
   raise ValueError('Atomic expansion text/origin changed')
  quotes=[p['quote'] for sid,pids in row['passage_ids'].items() for p in card[sid]['passages'] if p['id'] in pids]
  parent=x['source']['quote']
  if not any(' '.join(parent.split())==' '.join(q.split()) for q in quotes):
   raise ValueError('Atomic expansion parent is not its exact cited source paragraph')
  if x['occurrence_index']!=r['occurrence_index'] or x['occurrence_count']!=r['occurrence_count']:
   raise ValueError('Atomic occurrence expansion map changed')
 return {'reference_key':KEY,'source_template_lock':lock,'scope':'REQUESTED_CLEARING_ONLY; registered mechanical occurrence expansion; no scientific necessity certification','atomic_version':VERSION}

def bind_source(question,assessment):
 evidence=_read(HOME/'requested_clearing_projection_v1.json')
 check_source(question,assessment,evidence,KEY)
 return evidence

def paired(protocol,context,assessment,evidence):
 """Same function in prepare and import; never select a scope by score."""
 from oeq_simple_representation import from_catalog
 _locked()
 frozen=_read(HOME/'paired_requested_clearing_wash4.json')
 if hashlib.sha256(protocol.encode()).hexdigest()!=frozen['candidate']['source_sha256']:
  raise ValueError('Atomic pilot candidate differs from the reviewed Q13 occurrence/phase map')
 spec=importlib.util.spec_from_file_location('_frozen_idisco_atomic',HOME/'atomic_reference.py')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 cand=module.candidate(from_catalog(protocol,context['source_record_catalog'],assessment['extraction']))
 # Source rows are the frozen expansion, with all annotations kept; select both
 # sides together. Full antibody scenarios never become required task steps.
 ref=_read(HOME/'reference_full_wash4.json')
 result=module.select_scope({'candidate':cand,'reference':ref},'requested_clearing')
 if result!=frozen:raise ValueError('Atomic paired reconstruction differs from reviewed scope/occurrence map')
 return result
