"""Separate exact-source transport derivation. Never overwrites original inputs."""
from copy import deepcopy
import re

def occurrences(text,quote):
 return [m.start() for m in re.finditer(re.escape(quote),text)] if quote else []

def derive(raw,protocol):
 result=deepcopy(raw);events=[]
 def walk(node,path=''):
  if isinstance(node,list):
   for i,v in enumerate(node):walk(v,path+'/'+str(i))
  elif isinstance(node,dict):
   if set(node)=={'start','end','quote'} and protocol[node['start']:node['end']]!=node['quote']:
    hits=occurrences(protocol,node['quote'])
    if len(hits)!=1:raise ValueError('Nonunique or absent exact quote: '+path)
    before=deepcopy(node);node.update(start=hits[0],end=hits[0]+len(node['quote']))
    events.append({'path':path,'rule':'UNIQUE_EXACT_UNCHANGED_QUOTE_REANCHOR_ONLY','before':before,'after':deepcopy(node)})
   else:
    for k,v in node.items():walk(v,path+'/'+k)
 walk(result)
 for i,row in enumerate(result['extraction']['labels']):
  quote=row['quote'];anchors=occurrences(protocol,quote)
  for field,support in row['field_support'].items():
   spans=support['spans']
   if not spans:continue
   if any(all(a<=s['start'] and s['end']<=a+len(quote) for s in spans) for a in anchors):continue
   if len(anchors)!=1 or len(spans)!=1:raise ValueError('Cannot prove unique record for local support')
   anchor=anchors[0];prior=spans[0]
   if not (prior['start']<=anchor and anchor+len(quote)<=prior['end']):raise ValueError('Original support does not enclose original record')
   raw_value=support.get('raw_value')
   if support.get('kind')!='EXPLICIT' or support.get('transform')!='IDENTITY' or row[field]!=raw_value:raise ValueError('Only unchanged explicit identity values may narrow')
   hits=occurrences(quote,raw_value)
   selected_quote=raw_value
   if field in ['target','fluorophore'] and row.get('target') and row.get('fluorophore'):
    pairs=list(re.finditer(re.escape(row['target'])+r'\s*\+\s*'+re.escape(row['fluorophore']),quote))
    if len(pairs)!=1:raise ValueError('Label target/fluorophore attribution is not uniquely explicit')
    selected_quote=pairs[0].group();hits=[pairs[0].start()]
   if len(hits)!=1:raise ValueError('Value is not unique within unique original record')
   new={'start':anchor+hits[0],'end':anchor+hits[0]+len(selected_quote),'quote':selected_quote}
   assert protocol[new['start']:new['end']]==new['quote'] and raw_value in new['quote']
   support['spans']=[new]
   events.append({'path':f'/extraction/labels/{i}/field_support/{field}/spans/0','rule':'UNIQUE_RECORD_EXACT_ATTRIBUTED_LOCAL_SUPPORT_NARROWING','before':prior,'after':deepcopy(new),'unique_record_span':[anchor,anchor+len(quote)],'raw_value_unchanged':raw_value,'record_quote_unchanged':quote})
 return result,events
