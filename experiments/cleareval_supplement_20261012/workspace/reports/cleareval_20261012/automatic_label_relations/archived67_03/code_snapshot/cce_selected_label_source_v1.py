"""Source-only extraction of explicit chosen-label lists.

This bounded development candidate reads complete source text. It does not read
case IDs, model scores, author annotations or antibody-clone lookup tables.
Each label relation retains its exact source span and interpretation rule.
"""
from __future__ import annotations
import re

VERSION='selected-label-source-v1.1'
AF=re.compile(r'(?<![A-Za-z0-9])(?:Alexa\s*Fluor|AF)(?:\s*(?:[（(]\s*)?(\d{3})(?:\s*[）)])?)?(?![A-Za-z0-9])',re.I)
HEADER=re.compile(r'\bChosen\s+Label(?:l?ing|s)?\b|(?:所选|已选)[^:\n：]*?(?:荧光|标记)',re.I)
UNCERTAIN=re.compile(r'\b(?:or|optional|alternatively|not|without)\b|e\.g\.|例如|可选|任选|或者|不采用|不使用|未选',re.I)
ACTION=re.compile(r'\bincubat\w*\b|孵育|二抗|imaging\s+channels|成像通道',re.I)


def evidence(doc,unit,start=None,end=None):
    start=unit['start'] if start is None else start
    end=unit['end'] if end is None else end
    return {'unit_id':unit['unit_id'],'start':start,'end':end,
            'quote':doc['text'][start:end],'answer_sha256':doc['answer_sha256']}


def split_items(text):
    """Only top-level separators separate selected channels."""
    depth=0;start=0;parts=[]
    for i,c in enumerate(text):
        if c in '(（[':depth+=1
        elif c in ')）]':depth=max(0,depth-1)
        elif c in ',，;；、' and depth==0:
            parts.append((start,i,text[start:i]));start=i+1
    parts.append((start,len(text),text[start:]))
    return parts


def normalized(value):
    return re.sub(r'[\s_\-–—]+','',str(value)).casefold()


def catalog_identity_ambiguity(target,target_catalog):
    if normalized(target) in {normalized(name) for name in target_catalog}:return None
    parsed=re.fullmatch(r'([^()（）]+)\s*[（(]([^()（）]+)[）)]',target)
    if not parsed:return None
    left,right=[normalized(v.strip()) for v in parsed.groups()]
    parents={normalized(re.split(r'[（(]',name)[0].strip()):name for name in target_catalog}
    if left in parents and right in parents and left!=right:
        return {'outer_catalog_target':parents[left],'inner_catalog_target':parents[right],
                'reason':'two separate catalog target names are combined; no alias identity established'}
    return None


def extract(doc,policy,target_catalog=()):
    headers=[]
    for unit in doc['units']:
        text=doc['text'][unit['start']:unit['end']]
        if HEADER.search(text):
            match=re.search(r'\[([^\[\]]+)\]',text)
            if match:headers.append((unit,match))
    result={'version':VERSION,'answer_sha256':doc['answer_sha256'],
        'relations':[],'issues':[],'header_candidates':len(headers),
        'ready':False,'new_model_calls':0,'new_per_answer_author_annotations':0,
        'independent_evaluator':False,'expert_validated':False,
        'scope':'explicit chosen-label list; no claim of universal biological relation extraction'}
    if len(headers)!=1:
        result['issues'].append({'kind':'unique_chosen_label_list_unavailable'});return result
    unit,match=headers[0];body=match[1]
    result['header_source']=evidence(doc,unit)
    if UNCERTAIN.search(body) or UNCERTAIN.search(doc['text'][unit['start']:unit['start']+match.start()]):
        result['issues'].append({'kind':'selected_list_contains_alternatives_or_nonuse'});return result
    standalone={n for v in policy['standalone_types'].values() for n in v}
    standalone=sorted(standalone,key=lambda n:(-len(n),n))
    for lo,hi,part in split_items(body):
        offset=unit['start']+match.start(1)+lo
        span=evidence(doc,unit,offset,offset+len(part))
        cleaned=part.strip().strip('*').strip()
        dyes=list(AF.finditer(cleaned))
        if len(dyes)==1:
            dye=dyes[0];left=cleaned[:dye.start()].strip()
            if not left.endswith('+'):
                result['issues'].append({'kind':'no_explicit_target_plus_fluor_relation','source':span});continue
            target=left[:-1].strip();source_target=target;qualifier=None
            if not target or '+' in target or '/' in target:
                result['issues'].append({'kind':'multiple_or_uninterpretable_target','source':span});continue
            # The native-signal qualifier describes GFP's role; it is not part
            # of the antibody target's molecular name in an explicit GFP+AF pair.
            for native in policy['standalone_types']['native_fluorescent_protein']:
                if re.fullmatch(re.escape(native)+r'\s*[（(](?:内源(?:荧光)?|endogenous|native(?: fluorescence)?)[）)]',target,re.I):
                    target=native;qualifier='native-signal description separated from target identity';break
            ambiguous=catalog_identity_ambiguity(target,target_catalog)
            if ambiguous:
                result['issues'].append({'kind':'multiple_catalog_target_identities','source':span,**ambiguous});continue
            suffix=cleaned[dye.end():].strip()
            if suffix and not re.fullmatch(r'[（(][^()（）]*[）)]',suffix):
                result['issues'].append({'kind':'unparsed_fluor_suffix','source':span});continue
            result['relations'].append({'fluorophore':'Alexa Fluor'+(' '+dye[1] if dye[1] else ''),
                'marker':target,'source_spans':[span],
                'basis':'explicit selected target + fluorophore; antibody carrier/clone not required',
                'source_target_literal':source_target,'target_role_qualifier':qualifier,'source_fluor_literal':dye[0],
                'clone_identity_inferred':False,'generic_AF':dye[1] is None})
        elif dyes:
            result['issues'].append({'kind':'multiple_fluors_in_one_unsplit_item','source':span})
        else:
            found=next((n for n in standalone if re.fullmatch(re.escape(n)+r'(?:\s*[（(][^()（）]*[）)])?',cleaned,re.I)),None)
            if found:
                result['relations'].append({'fluorophore':found,'marker':'','source_spans':[span],
                    'basis':'explicit standalone signal in chosen list; external target-pair channel not applicable',
                    'source_fluor_literal':cleaned,'clone_identity_inferred':False,'generic_AF':False})
            else:result['issues'].append({'kind':'chosen_item_needs_body_relation','source':span})
    # A single generic AF channel may be concretized by the one actual AF reagent
    # selected in operations. Exemplary/optional statements never choose a dye.
    generic=[r for r in result['relations'] if r['generic_AF']]
    targeted=[r for r in result['relations'] if r['marker']]
    actual=[]
    for other in doc['units']:
        if other['unit_id']==unit['unit_id']:continue
        text=doc['text'][other['start']:other['end']]
        if ACTION.search(text) and not UNCERTAIN.search(text):
            for dye in AF.finditer(text):
                if dye[1]:actual.append({'fluorophore':'Alexa Fluor '+dye[1],
                    'source':evidence(doc,other),'literal':dye[0]})
    result['actual_AF_operation_evidence']=actual
    choices=sorted({a['fluorophore'] for a in actual})
    if len(generic)==1 and len(targeted)==1 and len(choices)==1:
        relation=generic[0];relation['fluorophore']=choices[0]
        relation['source_spans'].extend(a['source'] for a in actual if a['fluorophore']==choices[0])
        relation['basis']+='; single generic AF channel refined by uniquely selected operational dye'
        relation['generic_AF_refined']=True
    elif generic and len(choices)>1:
        result['issues'].append({'kind':'multiple_actual_AF_dyes_for_generic_channel','choices':choices})
    if not generic and len(targeted)==1 and choices and any(x!=targeted[0]['fluorophore'] for x in choices):
        result['issues'].append({'kind':'header_and_actual_AF_choice_need_reconciliation','choices':choices})
    result['ready']=bool(result['relations']) and not result['issues']
    result['selection_uses_achieved_score']=False
    return result
