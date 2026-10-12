"""Source-supported routine removal/continuation and antibody blocking support.

Only annotates already-returned labeling_preparation records. Does not alter
raw phase, duration, scope, repetition or operation membership.
"""
import copy,re,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_noncore_time_scope_v2 as previous
g=previous.g
VERSION='source-context-noncore-time-scope-v3'
TOP=re.compile(r'^\s*(?:#{1,6}\s*)?(\d+)[.)]?\s+([^\n]+?)\s*$')
CHILD=re.compile(r'^\s*(\d+)\.\d+(?:\.\d+)*\s+')
WASH_TITLE=re.compile(r'^(?:washing|wash(?:es)?|rinsing)\s*$',re.I)
BLOCK_TITLE=re.compile(r'^(?:blocking|antibody\s+blocking)\s*$',re.I)
ANTIBODY_TITLE=re.compile(r'^(?:(?:primary|secondary)\s+)?antibody\s+(?:incubation|staining|labeling)\s*$',re.I)
CORE=previous.previous.CORE
REMOVE=re.compile(r'\b(?:remove|removing|wash\s+(?:out|away)|rinse\s+(?:out|away))\b.*?\b(?:unbound|excess|residual)\s+(?:(?:primary|secondary)\s+)?(?:antibod(?:y|ies)|dyes?|stains?)(?:[/\s]+(?:antibod(?:y|ies)|dyes?|stains?))?',re.I)
REMOVAL_FIXATIVE=re.compile(r'\b(?:remove|removing|wash\s+out|rinse\s+out)\b.*?\b(?:residual|remaining|excess)\s+fixative\b',re.I)
ANTIBODY_ACTION=re.compile(r'\bincubat\w*\s+with\s+(?:(?:primary|secondary)\s+)?antibod(?:y|ies)\b',re.I)
BLOCK_BUFFER=re.compile(r'\bincubat\w*\s+with\s+blocking\s+buffer\b',re.I)
UNKNOWN=re.compile(r'permeabili|\b(?:optional|either|instead|alternative)\b',re.I)

def fullspan(op,unit,doc):
 s=op['operation'];a=unit['start']+len(unit['text'])-len(unit['text'].lstrip());b=unit['end']-(len(unit['text'])-len(unit['text'].rstrip()))
 return s['unit_id']==unit['unit_id'] and s['start']==a and s['end']==b and s['quote']==doc['text'][a:b]

def medium(text):
 text=CHILD.sub('',text.strip(),count=1)
 m=re.match(r'(?:incubat\w*\s+with|wash\w*\s+with|rinse\w*\s+with)\s+(fresh\s+)?(.+?)(?=\s+(?:to|with|for)\b|[.(,;]|$)',text,re.I)
 if not m:return None
 return {'fresh':bool(m[1]),'literal':re.sub(r'\s+',' ',m[2].strip()).casefold()}

def direct_removal(text):
 if CORE.search(text) or UNKNOWN.search(text):return None
 if REMOVE.search(text):return 'explicit_removal_of_unbound_labeling_reagents'
 if re.search(r'\bPBS\b|phosphate[- ]buffered\s+saline',text,re.I) and REMOVAL_FIXATIVE.search(text):return 'explicit_PBS_removal_of_residual_fixative'
 return None

def support(op,audit,doc):
 s=op['operation'];units=doc['units'];index=next((i for i,u in enumerate(units) if u['unit_id']==s['unit_id']),None)
 if index is None or not fullspan(op,units[index],doc):return None
 text=s['quote'];phase=op.get('phase_support',{})
 if phase.get('possible_core_function') or CORE.search(text) or UNKNOWN.search(text):return None
 direct=direct_removal(text)
 if direct:return {'basis':direct,'evidence':[copy.deepcopy(s)]}
 child=CHILD.match(text)
 if not child:return None
 parent=child[1];heading_index=None;heading=None
 for n in range(index-1,-1,-1):
  m=TOP.fullmatch(units[n]['text'].strip())
  if m:heading_index=n;heading=m;break
 if heading is None or heading[1]!=parent:return None
 if WASH_TITLE.fullmatch(heading[2]):
  m=medium(text)
  if not m or not m['fresh']:return None
  previous_index=next((n for n in range(index-1,heading_index,-1) if units[n]['text'].strip()),None)
  if previous_index is None:return None
  prior=units[previous_index];pchild=CHILD.match(prior['text']);pm=medium(prior['text'])
  if not pchild or pchild[1]!=parent or not pm or pm['literal']!=m['literal']:return None
  why=direct_removal(prior['text'])
  if not why:return None
  return {'basis':'same_numbered_washing_section_fresh_same_literal_medium_after_explicit_removal',
   'same_medium_literal':m['literal'],'evidence':[copy.deepcopy(units[heading_index]),copy.deepcopy(prior),copy.deepcopy(s)]}
 if BLOCK_TITLE.fullmatch(heading[2]) and BLOCK_BUFFER.search(text):
  next_index=next((n for n in range(index+1,len(units)) if units[n]['text'].strip()),None)
  if next_index is None:return None
  next_title=TOP.fullmatch(units[next_index]['text'].strip())
  if not next_title or not ANTIBODY_TITLE.fullmatch(next_title[2]):return None
  action_index=next((n for n in range(next_index+1,len(units)) if units[n]['text'].strip()),None)
  if action_index is None:return None
  action=units[action_index];achild=CHILD.match(action['text'])
  if not achild or achild[1]!=next_title[1] or not ANTIBODY_ACTION.search(action['text']) or CORE.search(action['text']):return None
  return {'basis':'source_blocking_buffer_section_immediately_precedes_explicit_antibody_incubation',
   'evidence':[copy.deepcopy(units[heading_index]),copy.deepcopy(s),copy.deepcopy(units[next_index]),copy.deepcopy(action)]}
 return None

def derive_audit(original,doc):
 if original['source_binding']['source_id']!=doc['source_id'] or original['source_binding']['answer_sha256']!=doc['answer_sha256'] or g.rawsha(doc['text'])!=doc['answer_sha256']:
  raise ValueError('SOURCE_IDENTITY_MISMATCH')
 audit=copy.deepcopy(original);changes=[]
 for op in audit['resolved']['operations']:
  if op['phase']!='labeling_preparation' or op['phase_support']['supported']:continue
  why=support(op,original,doc)
  if why:
   old=copy.deepcopy(op['phase_support']);op['phase_support']['supported']=True
   op['phase_support']['original_phase_support_v3']=old;op['phase_support']['source_context_support_v3']=why
   changes.append({'operation_id':op['id'],'original_phase_support':old,'raw_phase_unchanged':True,**why})
 before=copy.deepcopy(original['resolved']);after=copy.deepcopy(audit['resolved'])
 for part in [before,after]:
  for op in part['operations']:op.pop('phase_support',None)
 if before!=after or audit['inventory']!=original['inventory']:raise ValueError('NON_SUPPORT_STATE_CHANGED')
 audit['derived_noncore_scope_v3']={'version':VERSION,'changes':changes,'raw_phase_duration_repeat_scope_and_coverage_unchanged':True,'scientific_phase_confirmed':False}
 return audit,audit['derived_noncore_scope_v3']
