"""Shared surface normalization and explicit concentration assertion checks.

Input answers are immutable. Only parser copies are normalized, with reversible
span edits. Reference-anchored literal chemicals do not require a closed lexicon.
"""
import copy,re
from collections import defaultdict

VERSION='operation-evidence-robustness-20261102-v1'
SURFACE=re.compile(r'[\u2010-\u2015（）]|[ \t\u00a0\u202f]{2,}|[\t\u00a0\u202f]')

def normalize(text):
    pieces=[];edits=[];cursor=0;length=0
    for m in SURFACE.finditer(text):
        prefix=text[cursor:m.start()];pieces.append(prefix);length+=len(prefix)
        old=m[0];new='(' if old=='（' else ')' if old=='）' else '-' if '\u2010'<=old[0]<='\u2015' else ' '
        pieces.append(new);edits.append(dict(source=[m.start(),m.end()],normalized=[length,length+len(new)],original=old,replacement=new))
        length+=len(new);cursor=m.end()
    pieces.append(text[cursor:]);return ''.join(pieces),edits

def normalize_case(case):
    result=copy.deepcopy(case)
    for group in ['reference_steps','candidate_steps']:
        for step in result[group]:
            for key in ['text','heading']:
                if key not in step:continue
                original=step[key];step[key],edits=normalize(original)
                if edits:
                    step.setdefault('surface_source',{})[key]=original
                    step.setdefault('surface_edits',{})[key]=edits
    if 'answer' in result:
        # Full answer offsets are only used inside recipe extraction. Keep the
        # compact edit map so source claims can be mapped back without copies.
        result['answer'],result['_answer_surface_edits']=normalize(result['answer'])
    return result

def boundary(text,m):
    return not ((m['start'] and re.match(r'[A-Za-z0-9_]',text[m['start']-1])) or
                (m['end']<len(text) and re.match(r'[A-Za-z0-9_]',text[m['end']])))

STOP={'with','in','at','for','to','and','or','then','until','after','before','of','on','by','from',
      'concentration','temperature','time','solution','buffer','stock','final','working','full','medium'}

def percent_claims(text,method,e):
    """Bind each explicit percent occurrence; retain duplicate declarations."""
    ms=e.op.mentions(text,method);claims=[];unbound=[]
    purpose=re.search(r'\bto\s+(?:remove|wash)\b|洗去|去除',text,re.I)
    medium=re.search(r'\bMedium\s*:\s*([^;)\n]+)',text,re.I)
    medium_ids={m['id'] for m in e.op.mentions(medium[1],method)} if medium else set()
    primary=set(e.op.typed_operation(text,'',method)['primary_materials'])
    for q in e.recipes.QUANTITY.finditer(text):
        if '%' not in q[2]:continue
        if purpose and q.start()>purpose.start():continue
        ident=None;origin=None;literal=None
        labeled=bool(re.search(r'\bconcentration\s*:\s*$',text[:q.start()],re.I))
        if labeled:
            owners=medium_ids or primary
            if len(owners)==1:ident=next(iter(owners));origin='explicit_concentration_field'
        if ident is None:
            after=[m for m in ms if m['start']>=q.end() and m['start']-q.end()<12
                   and re.fullmatch(r'\s*(?:of\s+)?\(?\s*',text[q.end():m['start']])]
            before=[m for m in ms if m['end']<=q.start() and q.start()-m['end']<8
                    and re.fullmatch(r'[\s(:=]*',text[m['end']:q.start()])]
            if after:ident=after[0]['id'];origin='adjacent_material'
            elif before and not labeled:ident=before[-1]['id'];origin='adjacent_material'
        if ident is None and not labeled:
            tail=text[q.end():];match=re.match(r'\s*(?:of\s+)?([A-Za-z][A-Za-z0-9-]*(?:[ \t]+[A-Za-z][A-Za-z0-9-]*){0,4})',tail)
            words=[]
            if match:
                for word in match[1].split():
                    if word.lower() in STOP:break
                    words.append(word.lower())
            if words:
                literal=' '.join(words);ident='literal:'+literal.replace(' ','_');origin='reference_anchored_literal'
        claim=dict(value=float(q[1]),unit=e.recipes.unit(q[2]),span=[q.start(),q.end()],literal=q[0])
        if ident:claims.append(dict(claim,material=ident,origin=origin,chemical_literal=literal))
        else:unbound.append(claim)
    return claims,unbound

def compare(a,b):
    # Unspecified percent denotes the same nominal statement on BOTH sides;
    # this never converts a specified mass basis to a different/unknown basis.
    if a['unit']!=b['unit']:return 'UNKNOWN'
    return 'PASS' if abs(a['value']-b['value'])<1e-8 else 'FAIL'

def concentration_assertions(rs,cs,method,e):
    rr,ru=percent_claims(rs['text'],method,e);cc,cu=percent_claims(cs['text'],method,e)
    checks={};details={};by=defaultdict(list)
    for c in cc:by[c['material']].append(c)
    # Only a labeled declaration claims to restate the same scalar operation
    # concentration. Multiple prose values may describe a real gradient.
    for material,values in by.items():
        labels=[v for v in values if v['origin']=='explicit_concentration_field']
        prose=[v for v in values if v['origin']!='explicit_concentration_field']
        if labels and prose:
            states=[compare(a,b) for a in labels for b in prose]
            field='concentration:internal:'+material
            checks[field]=e.combine(states);details[field]=dict(claims=values)
    for claim in rr:
        if not claim['material'].startswith('literal:'):continue
        field='concentration:'+claim['material'];values=by[claim['material']]
        states=[compare(claim,c) for c in values]
        checks[field]=e.combine(states) if states else 'UNKNOWN'
        details[field]=dict(reference=claim,candidate_claims=values)
    if ru:
        checks['concentration:reference_claim_coverage']='UNKNOWN'
        details['concentration:reference_claim_coverage']=dict(unbound_reference_claims=ru)
    return checks,details

def install(e):
    if getattr(e,'robustness_version',None)==VERSION:return
    e.robustness_version=VERSION
    old_mentions=e.op.mentions
    def mentions(text,method):return [m for m in old_mentions(text,method) if boundary(text,m)]
    e.op.mentions=mentions
    old_checks=e.checks
    def checks(rs,cs,rg,cg,method,**kw):
        result=old_checks(rs,cs,rg,cg,method,**kw)
        extra,_=concentration_assertions(rs,cs,method,e);result.update(extra)
        return result
    e.checks=checks
