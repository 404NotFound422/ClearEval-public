"""Generic source-linked requirement merger. No candidate text is read here."""
import re,copy,hashlib,json
VERSION='source-linked-parameter-slots-v2-20261015'
def norm(x):return re.sub(r'\s+',' ',re.sub(r'[‐‑‒–—−_]','-',x)).strip().casefold()
def validate_contract(contract,sources):
 passages={(c['id'],p['id']):p['quote'] for c in sources for p in c['passages']};seen=set()
 for row in contract['requirements']:
  if row['id'] in seen:raise ValueError('Duplicate source requirement ID')
  seen.add(row['id']);text=passages[(row['source_card_id'],row['passage_id'])]
  if not row['quote'] or row['quote'] not in text:raise ValueError('Source requirement quote mismatch '+row['id'])
  if row['condition_quote'] is not None and row['condition_quote'] not in text:raise ValueError('Condition quote mismatch '+row['id'])
  if row['applicability'] not in {'REQUIRED_PROCEDURE_SPECIFICATION','CONDITIONAL','OPTIONAL'}:raise ValueError('Unknown applicability')
  phases=row.get('phase_scope');phases=phases if isinstance(phases,list) else [phases]
  if not phases or any(x not in {'DEHYDRATION','RI_MATCHING','CLEARING','STORAGE','PREPARATION'} for x in phases):raise ValueError('Unknown phase scope')
  if row['scope_unit'] not in {'OPERATION','ROUTE'}:raise ValueError('Unknown scope')
  if row['selector']['kind'] not in {'NAME','ROLE'}:raise ValueError('Unknown selector')
 return contract

def matches(op,selector):
 text=norm(op.get('raw_text',op['operation']))
 if selector['kind']=='NAME':
  return any(re.search(r'(?<![\w-])'+re.escape(norm(n))+r'(?![\w-])',text) for n in selector['values'])
 role=op.get('operation_role');phase=norm(op.get('phase',''))
 for v in selector['values']:
  if v==role or norm(v)==phase:return True
  if v=='clearing' and role in {'dehydration','ri_matching','mixed_solvent_exchange','pure_solvent_wash'}:return True
  if v=='clearing' and role is None and re.search(r'\bincubat',text) and 'storage' not in phase:return True
 return False

def phase_matches(op,scope):
 if isinstance(scope,list):return any(phase_matches(op,s) for s in scope)
 role=op.get('operation_role');phase=norm(op.get('phase',''));text=norm(op.get('raw_text',op['operation']))
 if scope=='PREPARATION':return True
 if scope=='STORAGE':return role=='storage' or 'storage' in phase
 if scope=='DEHYDRATION':return role=='dehydration' or 'dehydration' in phase
 if scope=='RI_MATCHING':return role=='ri_matching' or phase in {'ri-matching','ri matching'}
 if scope=='CLEARING':return role in {'dehydration','ri_matching','mixed_solvent_exchange','pure_solvent_wash'} or (role is None and 'storage' not in phase and bool(re.search(r'\bincubat',text)))
 return False

def bind_operation_source(op,sources,requirements):
 """Fail closed before computing a partial denominator; never infer a route by role."""
 anchor=op.get('source',{}); matches_cards=[]
 for card in sources:
  doc=card.get('source_document',{});text=doc.get('text','')
  digest=hashlib.sha256(text.encode()).hexdigest()
  if not text or doc.get('sha256')!=digest:raise ValueError('Invalid source document hash: '+card['id'])
  if anchor.get('text_sha256')!=digest:continue
  start,end=anchor.get('start'),anchor.get('end');quote=anchor.get('quote')
  if not isinstance(start,int) or not isinstance(end,int) or not quote or text[start:end].strip()!=quote.strip():continue
  matches_cards.append(card)
 if len(matches_cards)!=1:raise ValueError('UNSUPPORTED_SOURCE_SCOPE: unbound or ambiguous operation '+op['id'])
 card=matches_cards[0];scoped=[r for r in requirements if r['source_card_id']==card['id']]
 if not scoped:raise ValueError('UNSUPPORTED_SOURCE_SCOPE: unreviewed operation '+op['id']+' source '+card['id'])
 passage_ids={p['id'] for p in card['passages']}
 if any(pid not in passage_ids for pid in op.get('source_passage_ids',[])):raise ValueError('UNSUPPORTED_SOURCE_SCOPE: unknown linked passage '+op['id'])
 applicable=[r for r in scoped if matches(op,r['selector']) and phase_matches(op,r['phase_scope'])]
 if not applicable:raise ValueError('UNSUPPORTED_SOURCE_SCOPE: uncovered operation or linked recipe '+op['id'])
 return scoped

def build_source_slots(payload,contract):
 from oeq_source_reference_scope import validate_reference_scope
 validate_reference_scope(payload)
 active_ids={c['id'] for c in payload['provided_sources']}
 contract=copy.deepcopy(contract);contract['requirements']=[r for r in contract['requirements'] if r['source_card_id'] in active_ids]
 if not contract['requirements']:raise ValueError('No reviewed source parameter contract for provided source')
 validate_contract(contract,payload['provided_sources']);refs=payload['paired_representation']['reference']['operations'];slots=[];excluded=[];seen={}
 for op in refs:
  if re.search(r'restor|re-clear|reclear|repeat.imaging',norm(op.get('phase','')+' '+op.get('operation_role',''))):
   raise ValueError('Restoration reference requires explicit triggered execution-context contract')
  if op.get('execution_status','ASSERTED_OPERATION')!='ASSERTED_OPERATION':
   excluded.append({'operation_id':op['id'],'reason':'REFERENCE_OPERATION_NOT_AFFIRMED'});continue
  scoped_requirements=bind_operation_source(op,payload['provided_sources'],contract['requirements'])
  # Explicit task-level parameter instructions apply to every referenced executable operation.
  base=[('medium','Named executable operation medium or supported functional substitute')]
  if 'KEY_TIMES' in payload.get('parameter_requirements',[]):base.append(('time_or_endpoint','Explicit candidate duration or executable termination criterion'))
  for dim,criterion in base:
   key=(op['id'],dim,None);seen[key]=len(slots);slots.append({'id':op['id']+':'+dim,'operation_id':op['id'],'dimension':dim,'subject':None,'operation_text':op.get('raw_text',op['operation']),'criterion':criterion,'source_requirements':[],'requirement_origin':'EXPLICIT_TASK_EXECUTION_PARAMETERS'})
  for req in scoped_requirements:
   if not matches(op,req['selector']) or not phase_matches(op,req['phase_scope']):continue
   if req['applicability']!='REQUIRED_PROCEDURE_SPECIFICATION':
    excluded.append({'operation_id':op['id'],'requirement_id':req['id'],'reason':req['applicability'],'condition_quote':req['condition_quote']});continue
   unit=('route:'+req['id']) if req['scope_unit']=='ROUTE' else op['id'];subject=req['subject'];dim=req['dimension'];key=(unit,dim,subject)
   # Enrich a generic task medium/time slot rather than duplicating it.
   if dim in {'medium','time_or_endpoint'} and (unit,dim,None) in seen:key=(unit,dim,None)
   if key not in seen:
    seen[key]=len(slots);sid=unit+':'+dim+(':'+re.sub(r'\W+','_',subject) if subject else '')
    slots.append({'id':sid,'operation_id':unit,'dimension':dim,'subject':subject,'operation_text':op.get('raw_text',op['operation']),'criterion':req['criterion'],'source_requirements':[],'requirement_origin':'SOURCE_LINKED_SCOPED_SPECIFICATION'})
   slots[seen[key]]['source_requirements'].append(copy.deepcopy(req))
 # Deduplicate same source requirement inherited from several operations into one route slot.
 for slot in slots:
  slot['source_requirements']=list({r['id']:r for r in slot['source_requirements']}.values())
  if slot['source_requirements']:slot['criterion']=' AND '.join(dict.fromkeys(r['criterion'] for r in slot['source_requirements']))
 return {'version':VERSION,'scope':payload['paired_representation'].get('scope'),'slots':slots,'denominator':len(slots),'excluded':excluded,'source_contract_sha256':hashlib.sha256(json.dumps(contract,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),'weighting':'One equal-weight explicit parameter dimension/ingredient per distinct operation; one-time reagent preparation once per route. Source recipes merged by named solution; no candidate answer read to choose denominator.','limitation':'Source-derived benchmark operationalization, not expert gold or universal scientific requirements. Conditional requirements excluded unless separately validated triggered-scope support is supplied; this version does not auto-trigger them.'}
