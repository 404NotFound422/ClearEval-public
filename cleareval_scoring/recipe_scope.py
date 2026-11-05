"""Keep recipe prose separate from specimen execution, retaining source spans."""
from copy import deepcopy
import re
from . import component,preparation

VERSION='recipe-execution-scope-20261105-v1'
NUMBER=r'\d+(?:\.\d+)?'


def parentheses(text):
    stack=[];out=[]
    for i,char in enumerate(text):
        if char in '(（[':stack.append(i)
        elif char in ')）]' and stack:
            start=stack.pop()
            if not stack:out.append((start,i+1))
    return out


def declaration(text,end):
    """Return the composition directly attached to a named stock."""
    tail=text[end:]
    qualifier=re.match(r'\s+(?:(?:clearing|stock|working|RI[- ]matching)\s+)?(?:solution|buffer|reagent|medium)(?:\s+(?:[IVX]+|[ABC]))?\b',tail,re.I)
    if qualifier:return declaration(text,end+qualifier.end())
    lead=len(tail)-len(tail.lstrip());start=end+lead
    if start<len(text) and text[start] in '(（[':
        spans=parentheses(text[start:])
        if spans and spans[0][0]==0:
            stop=start+spans[0][1]
            marker=text[start+1:stop-1].strip()
            if marker in {'N','M'} or (marker.isdigit() and re.match(r'\s+(?:solution|medium|reagent)\b',text[stop:],re.I)):
                return declaration(text,stop)
            return dict(span=[start,stop],text=text[start+1:stop-1])
    marker=re.match(r'\s*(?:[:：]|,?\s*(?:containing|contains?|consists? of|(?:is|was) (?:a )?mixture of|(?:is|was) prepared (?:with|from|by mixing))\b)\s*',tail,re.I)
    if not marker:return None
    start=end+marker.end();stop=len(text)
    # Subsequent operations and labeled conditions are not recipe ingredients.
    boundary=re.search(r';|；|\.(?!\d)|(?:[(（]\s*)?(?:Time|Temperature|时间|温度)\s*[:：]|,\s*(?:then\b|for\s+\d)',text[start:],re.I)
    if boundary:stop=start+boundary.start()
    return dict(span=[end,stop],text=text[start:stop])


def named_spans(text,method):
    names=[m for m in component.op.mentions(text,method) if m['id'] in component.op.FORMULATIONS]
    spans=[]
    for name in names:
        declared=declaration(text,name['end'])
        if not declared:continue
        body=declared['text']
        # Actual subsequent specimen actions remain executable even inside a
        # parenthesis. Mixing/storage of a stock is preparation, not exposure.
        if re.search(r'\b(?:incubat\w*|wash\w*|rins\w*|transfer\w*|immerse\w*)\b|孵育|清洗|转入|浸泡',body,re.I):continue
        has_quantity=component.recipes.QUANTITY.search(body) or re.search(r'\d\s*[:：]\s*\d|\d\s*(?:g|ml)\b',body,re.I)
        if not has_quantity:continue
        spans.append(dict(**declared,kind='named_stock_composition',stock=name['id']))
    return spans


def dilution_spans(text,method):
    found=[]
    for start,stop in parentheses(text):
        body=text[start+1:stop-1]
        volume=bool(re.search(r'\bvolumes?\b|vol/vol|v/v',body,re.I))
        dilution=bool(re.search(r'dilut|稀释',body,re.I))
        recipe=(volume or dilution) and bool(re.search(r'\+|\bto\b|\d\s*[:：]\s*\d',body))
        if not recipe:continue
        outside=component.concentration_fields(text[:start],method)
        inside=component.concentration_fields(body,method)
        shared=set(outside)&set(inside)
        if not shared:continue
        found.append(dict(span=[start,stop],text=body,kind='working_solution_preparation',materials=sorted(shared)))
    return found


def project_case(case):
    result=deepcopy(case);count=0
    for key in ['candidate_steps','reference_steps']:
        for step in result[key]:
            if preparation.role(step)=='reagent_preparation':continue
            text=step['text']
            spans=named_spans(text,case['method'])+dilution_spans(text,case['method'])
            unique={tuple(s['span']):s for s in spans}
            if not unique:continue
            masked=list(text)
            for start,stop in unique:masked[start:stop]=' '*(stop-start)
            step['_recipe_source_text']=text
            step['recipe_preparation_spans']=[dict(span=s['span'],kind=s['kind']) for s in unique.values()]
            step['text']=''.join(masked);count+=1
    return result,count


def restore_sources(packet):
    for step in packet['logical_candidate_steps']:
        if '_recipe_source_text' in step:step['text']=step.pop('_recipe_source_text')


def _quantity(text,material,method):
    for mention in component.op.mentions(text,method):
        if mention['id']!=material:continue
        quantities=[q for q in component.recipes.QUANTITY.finditer(text[:mention['start']])
                    if re.fullmatch(r'\s*',text[q.end():mention['start']])]
        if quantities:
            q=quantities[-1]
            return float(q[1]),component.recipes.unit(q[2])
    return None


def audit_dilutions(case):
    """Check explicit two-part volume arithmetic against the stated working %.

    This is a nominal recipe-consistency check, not a unit/density conversion.
    """
    out=[];method=case['method']
    for step in case['candidate_steps']:
        for span in dilution_spans(step['text'],method):
            text=span['text']
            text=re.sub(r'^\s*(?:配制|例如|prepared\s+(?:from|with)|preparation|e\.g\.)\s*[:：]?\s*','',text,flags=re.I)
            volumes=re.search(r'('+NUMBER+r')\s*volumes?\s+(.*?)\s*(?:\+|\bto\b)\s*('+NUMBER+r')\s*volumes?\s+(.*)',text,re.I)
            ratio=re.search(r'(.*?)\s*[:：]\s*(.*?)\s*=\s*('+NUMBER+r')\s*[:：]\s*('+NUMBER+r')',text,re.I)
            if volumes:parts=[(float(volumes[1]),volumes[2]),(float(volumes[3]),volumes[4])]
            elif ratio:parts=[(float(ratio[3]),ratio[1]),(float(ratio[4]),ratio[2])]
            else:parts=[]
            for material in span['materials']:
                working=_quantity(step['text'][:span['span'][0]],material,method)
                stock=[(v,_quantity(t,material,method)) for v,t in parts]
                stock=[(v,q) for v,q in stock if q is not None]
                state='UNKNOWN';expected=None;compatible=[]
                if working and len(stock)==1 and len(parts)==2:
                    volume,q=stock[0];total=sum(v for v,_ in parts)
                    if total>0 and q[1]==working[1] and q[1] in {'%v/v','%w/v','%unspecified'}:
                        expected=volume*q[0]/total
                        state='PASS' if abs(working[0]-expected)<1e-7 else 'FAIL'
                if not parts and working and re.search(r'dilut|稀释',text,re.I):
                    r=re.search(r'('+NUMBER+r')\s*[:：]\s*('+NUMBER+r')',text)
                    q=_quantity(text,material,method)
                    if r and q and q[1]==working[1] and q[1] in {'%v/v','%w/v','%unspecified'}:
                        a,b=float(r[1]),float(r[2])
                        if b>0 and a+b>0:
                            compatible=[q[0]*a/(a+b)]
                            if b>=a:compatible.append(q[0]*a/b)
                            # The explicitly stated working concentration
                            # disambiguates stock:diluent versus stock:total.
                            state='PASS' if any(abs(working[0]-x)<1e-7 for x in compatible) else 'FAIL'
                out.append(dict(candidate=step['id'],field='concentration:recipe_dilution:'+material,
                    status=state,working_percent=working[0] if working else None,
                    recipe_percent=expected,compatible_recipe_percent=compatible,source_span=span['span']))
    return out
