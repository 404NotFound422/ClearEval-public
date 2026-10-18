"""Opt-in source-bound parameter slots and explicit defect attribution.
No source values become candidate values. Unknown never counts as missing.
"""
import copy, hashlib, json, re
VERSION='structured-criteria-v2-20261015'
def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

# Detection admits dimensions only, never candidate values or a claim of necessity.
DIMENSIONS={
 'temperature':r'°\s*C|℃|\btemperature\b|\broom.temperature\b|below\s+\d+',
 'concentration':r'%|\b(molar|concentration|pure)\b|\b\d+(?:\.\d+)?\s*[mµμ]?M\b',
 'pH':r'\bpH\b', 'agitation':r'\b(shaking|agitat\w*|rocking)\b',
 'light_protection':r'\bdark\b|aluminum foil|light.protect',
 'container':r'\b(chambers?|tubes?|vials?|containers?)\b',
 'volume':r'\d+\s*(?:[–-]\s*\d+\s*)?mL\b',
}
def build_slots(payload):
 pair=payload['paired_representation']; refs=pair['reference']['operations']; slots=[]; excluded=[]
 for op in refs:
  state=op.get('execution_status','ASSERTED_OPERATION')
  if state!='ASSERTED_OPERATION':
   excluded.append({'operation_id':op['id'],'reason':'NONAFFIRMED_OR_CONDITIONAL_REFERENCE','status':state});continue
  text=op.get('raw_text',op['operation'])
  dims=['medium']
  if 'KEY_TIMES' in payload.get('parameter_requirements',[]):dims.append('time_or_endpoint')
  for k,pattern in DIMENSIONS.items():
   if re.search(pattern,text,re.I):dims.append(k)
  for dim in dims:
   slots.append({'id':op['id']+':'+dim,'operation_id':op['id'],'dimension':dim,
    'operation_text':text,'requirement_origin':('EXPLICIT_TASK_KEY_TIMES' if dim=='time_or_endpoint' else 'SCOPED_REFERENCE_OPERATION'),
    'source':copy.deepcopy(op.get('source',{})), 'source_passage_ids':op.get('source_passage_ids',[]),
    'assessment_rule':'Candidate must explicitly specify this dimension for this operation or explicitly scoped shared operation group. Any executable value counts for completeness, not correctness. A supported functional substitute may satisfy medium. A missing whole operation gives missing slots, not reference-value substitution.'})
 return {'version':VERSION,'scope':pair.get('scope'),'slots':slots,'denominator':len(slots),'excluded':excluded,
  'weighting':'One equal-weight dimension per distinct reference operation. Distinct serial baths retained; one explicit shared condition may support several separately applicable slots. No optional untriggered restoration or extra recommendations added.',
  'limitation':'Only source-supported selected reference scope; does not claim to cover every candidate-added operation or equal the prior free-form denominator. Alternative-route applicability must be established upstream; unresolved route yields UNKNOWN.'}

def object_schema(props):return {'type':'object','additionalProperties':False,'required':list(props),'properties':props}
def extend_schema(schema,manifest):
 s=copy.deepcopy(schema);s['required']+=['parameter_slot_review','correctness_attribution']
 item=object_schema({'status':{'type':'string','enum':['PRESENT','MISSING','UNKNOWN']},'candidate_quotes':{'type':'array','items':{'type':'string','minLength':1}},'reason':{'type':'string','minLength':1}})
 s['properties']['parameter_slot_review']=object_schema({x['id']:copy.deepcopy(item) for x in manifest['slots']})
 finding=object_schema({'component':{'type':'string','enum':['co_method','co_param']},'severity':{'type':'string','enum':['LOCAL','CRITICAL','UNRESOLVED']},'candidate_quote':{'type':'string','minLength':1},'evidence_basis':{'type':'string','minLength':1},'counterfactual':{'type':'string','enum':['METHOD_INCOMPATIBLE_AT_ANY_FEASIBLE_PARAMETERS','CHANGING_STATED_PARAMETER_CAN_ADDRESS','UNRESOLVED']},'reason':{'type':'string','minLength':1}})
 s['properties']['correctness_attribution']={'type':'array','items':finding}
 return s

PROMPT='''\nSTRUCTURED CRITERIA CONTRACT structured-criteria-v2-20261015 (takes precedence for overlapping rules).
Every slot now contains source-linked criterion and source_requirements. Apply that exact scoped criterion, not mere occurrence of a number. A recipe formulation_component requires explicit ingredient identity plus its concentration for that named solution; carrier requires explicit solvent/buffer. Final solution pH is not established by precursor water pH. In particular, THF in pH-adjusted water does not by itself specify final THF-solution pH. Do not assume mixing preserves precursor pH. Source statements support what should be specified, never what the candidate actually specified.
C_param: do NOT invent a denominator or free-hand the 80% threshold. For every fixed parameter_slots.slots entry, provide parameter_slot_review under that exact ID. PRESENT requires one or more exact nonempty substrings of unchanged_protocol establishing an executable candidate value and its scope. Use actual candidate values even when they differ from the publication; correctness is separate. Never cite a source value as candidate evidence. Shared candidate text can satisfy several slots only when explicitly applying to them. MISSING means confidently absent; UNKNOWN means unresolved applicability, selection, scope or grounding, not confidently absent. Do not silently repair extraction disagreement: identify it in reason, and use explicit unambiguous unchanged_protocol only. Alternate methods may meet a functional slot only when substitution is supported; otherwise UNKNOWN. Do not add optional recommendations, conditional untriggered restoration or extra dimensions to the fixed denominator.
For c_param.score, report the mechanical rule: if any slot UNKNOWN then null with missing_reason; otherwise PRESENT/total >=0.8 =>3; below 0.8 with all medium and time_or_endpoint slots PRESENT =>2; other positive PRESENT count =>1; none PRESENT =>0. Empty denominator =>null. This is an explicitly fixed-slot operationalization of prior bands; do not pretend it is numerically identical to earlier free-form judgments.
For co_method/co_param supply correctness_attribution with every actual deduction or substantive uncertainty (empty array if none). Classify root causes by a counterfactual: incompatibility of the chosen strategy even at feasible parameter values under the fixed task/sample/label constraints (not universal chemical impossibility) goes to co_method; a problem with a specific duration, concentration, temperature or exposure that could be addressed by changing that parameter goes to co_param. Do not move the same concern between components or duplicate it. If the counterfactual cannot be established, record UNRESOLVED and preserve affected uncertainty. Mentioning a parameter in a strategy criticism is insufficient to assert failure at every feasible value. For each component, critical finding=>0; otherwise unresolved=>null; otherwise local=>1; no finding=>2. Co_order and Co_chem remain independent under the original rubric. Do not balance a deduction in one component by upgrading another.
Label review: bind task coverage and distinction to the explicitly selected scheme. If an optional label is essential to meeting the task, establish whether the answer actually selects it; if not resolvable use UNKNOWN, not silently selected or absent. Necessary distinction requires explicit task outcome attribution; overlapping fluorophore spectra alone do not prove an independent-channel requirement. Missing specifications remain UNKNOWN in the review; never assert successful separation. Do not alter target coverage or compatibility to compensate.
'''

def repair_request(text,contract=None):
 head,body=text.split('\nSCORING_INPUT_JSON\n',1);p=json.loads(body)
 from oeq_source_parameter_slots import build_source_slots
 if contract is None:
  from pathlib import Path
  contract=json.loads((Path(__file__).parent/'source_parameter_contract.json').read_text())
 m=build_source_slots(p,contract);p['parameter_slots']=m;p['score_output_schema']=extend_schema(p['score_output_schema'],m)
 return head+PROMPT+'\nSCORING_INPUT_JSON\n'+json.dumps(p,ensure_ascii=False,sort_keys=True,separators=(',',':')),p

def replay(proposal,payload):
 """Returns adopted copy plus audit; raw proposals remain immutable."""
 import jsonschema
 jsonschema.validate(proposal,payload['score_output_schema']);p=copy.deepcopy(proposal);manifest=payload['parameter_slots'];states=[];present=0;key_complete=True
 for slot in manifest['slots']:
  r=p['parameter_slot_review'][slot['id']];state=r['status'];quotes=r['candidate_quotes']
  if state=='PRESENT' and not quotes:raise ValueError('PRESENT needs candidate quote '+slot['id'])
  if any(q not in payload['unchanged_protocol'] for q in quotes):raise ValueError('Ungrounded candidate quote '+slot['id'])
  if state=='MISSING' and quotes:raise ValueError('MISSING cannot have positive candidate quote '+slot['id'])
  states.append(state);present+=state=='PRESENT'
  if slot['dimension'] in ('medium','time_or_endpoint') and state!='PRESENT':key_complete=False
 n=len(states);grade=None if not n or 'UNKNOWN' in states else 3 if present/n>=.8 else 2 if key_complete else 1 if present else 0
 out={'score':grade,'reasoning':f'Fixed applicable slots: {present}/{n} PRESENT; {states.count("UNKNOWN")} UNKNOWN. No reference values copied.'}
 if grade is None:out['missing_reason']='Unresolved applicable slot or empty denominator'
 p['scores']['completeness']['c_param']=out
 for component in ['co_method','co_param']:
  findings=[f for f in p['correctness_attribution'] if f['component']==component]
  for f in findings:
   if f['candidate_quote'] not in payload['unchanged_protocol']:raise ValueError('Ungrounded correctness quote')
   expected={'METHOD_INCOMPATIBLE_AT_ANY_FEASIBLE_PARAMETERS':'co_method','CHANGING_STATED_PARAMETER_CAN_ADDRESS':'co_param'}.get(f['counterfactual'])
   if expected and expected!=component:raise ValueError('Wrong defect attribution')
   if f['counterfactual']=='UNRESOLVED' and f['severity']!='UNRESOLVED':raise ValueError('Unresolved counterfactual cannot become known severity')
  severities=[f['severity'] for f in findings];g=0 if 'CRITICAL' in severities else None if 'UNRESOLVED' in severities else 1 if 'LOCAL' in severities else 2
  r={'score':g,'reasoning':'Structured root-cause attribution: '+('; '.join(f['reason'] for f in findings) or 'No supported defect identified'),'evidence_basis':'; '.join(f['evidence_basis'] for f in findings) or 'MODEL_JUDGMENT: no supported defect identified'}
  if g is None:r['missing_reason']='Unresolved substantive defect attribution'
  p['scores']['correctness'][component]=r
 return p,{'version':VERSION,'denominator':n,'present':present,'unknown':states.count('UNKNOWN'),'coverage':present/n if n else None,'raw_scores_preserved_separately':True,'rubric_change':'EXPLICIT_SLOT_OPERATIONALIZATION_NOT_NUMERICAL_EQUIVALENCE'}
