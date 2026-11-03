"""Condition evidence with explicit ownership, bounds, endpoints and mixtures."""
import re, math
WORDS={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'twelve':12,'twenty-four':24}
def normalize_words(text):
    for word,value in WORDS.items():
        text=re.sub(r'\b'+word+r'\b(?=\s*(?:to\b|[-–]|hours?\b|days?\b|minutes?\b|seconds?\b))',str(value),text,flags=re.I)
    # Convert "one to two days" after the first pass without changing unrelated numbers.
    text=re.sub(r'(\d+)\s+to\s+(\d+)\s*(hours?|days?|minutes?|seconds?)',r'\1-\2 \3',text,flags=re.I)
    return text
def endpoint(text):
    m=re.search(r'(?:until|直至|直到)\s*(?:the\s+)?(?:samples?|tissues?)?\s*(?:become(?:s)?|is|are)?\s*(?:optically\s+)?(?:transparent|clear|透明)',text,re.I)
    return {'value':'UNTIL_CLEAR','kind':'endpoint','evidence':m[0]} if m else None
def parse(text,name,legacy):
    normalized=normalize_words(text)
    # Refresh/secondary scheduling clauses are not the principal contact duration.
    if name=='duration':
        conditional=re.search(r'most samples|larger .*longer|may take longer',normalized,re.I)
        ep=endpoint(normalized)
        if conditional and ep:return ep
        primary=re.split(r';\s*(?:if|repeat|refresh|replace)|；\s*(?:如果|重复|更换)',normalized,flags=re.I)[0]
        primary=re.sub(r'\s+according to (?:the )?sample size','',primary,flags=re.I)
        result=legacy(primary,name)
        if result['value'] is None and ep and not re.search(r'\d+\s*(?:h|hr|hour|min|day|天|小时)',primary,re.I):return ep
    else:result=legacy(normalized,name)
    result=dict(result)
    result['evidence_text']=text
    # A labelled condition is an assertion, not permission to overwrite a contrary
    # principal-operation assertion. Restrict to body before the labelled block.
    label='Time|时间' if name=='duration' else 'Temperature|温度'
    tagged=re.search(r'(?:'+label+r')\s*[:：]',normalized,re.I)
    if tagged:
        start=normalized.rfind('(',0,tagged.start());start=max(start,normalized.rfind('（',0,tagged.start()))
        body=normalized[:start] if start>=0 else normalized[:tagged.start()]
        # Remove other labelled fields from the residual text.
        body=re.sub(r'\b(?:Temperature|Time|温度|时间)\s*[:：][^;,)）]*','',body,flags=re.I)
        other=legacy(body,name)
        if other.get('value') is not None and result.get('value') is not None and other['kind'] not in ('symbolic','alternatives') and result['kind'] not in ('symbolic','alternatives'):
            if other['value']!=result['value'] and re.search(r'\bfor\b|\bat\b|孵育|持续',body,re.I):
                result={'value':None,'kind':'conflict','assertions':[other,result],'evidence_text':text}
    return result
def compare(reference,candidate,legacy):
    if candidate['kind']=='conflict':return 'FAIL'
    if reference['kind']=='conflict':return 'UNKNOWN'
    if reference['kind']=='endpoint':
        return 'PASS' if candidate['kind']=='endpoint' and candidate['value']==reference['value'] or endpoint(candidate.get('evidence_text','')) else 'UNKNOWN'
    if reference['kind']=='lower_strict' and isinstance(candidate.get('value'),list):
        # Equality does not satisfy a strict lower bound.
        if candidate['value'][1]<=reference['value'][0]:return 'FAIL'
    return legacy(reference,candidate)
def agitation(text):
    """Mode predicates preserve negation and distinguish rotation from shaking."""
    raw=text
    modes={'shake':r'shak\w*|摇动|摇晃|轻摇|摇床|振荡','rotate':r'rotat\w*|rotor|旋转|转动'}
    positive=set();negative=set()
    for mode,pat in modes.items():
        for m in re.finditer(pat,text,re.I):
            prefix=text[max(0,m.start()-22):m.start()]
            if re.search(r'(?:without|do not|never|no|not)\s*$|(?:不要|不|无|禁止)\s*$',prefix,re.I):negative.add(mode)
            else:positive.add(mode)
    if re.search(r'静置|without agitation|stationary|no agitation|静止',text,re.I):negative.update(modes)
    return {'positive':sorted(positive),'negative':sorted(negative),'evidence_text':raw}
def agitation_check(reference,candidate):
    r,c=agitation(reference),agitation(candidate)
    rp,rn,cp,cn=map(set,[r['positive'],r['negative'],c['positive'],c['negative']])
    if cp&cn:return 'FAIL'
    if rn&cp:return 'FAIL'
    if rp:
        # The source must explicitly permit an alternative agitation mode.
        allowed=rp
        if cp&allowed:return 'PASS'
        if cn>=allowed:return 'FAIL'
        return 'UNKNOWN'
    if rn:
        if cn>=rn:return 'PASS'
        if cp and not cp&rn:return 'PASS'
        return 'UNKNOWN'
    return None
def ratio_fields(text,mentions):
    """Two named liquids with an explicit ordered ratio; retain arithmetic evidence."""
    match=re.search(r'(?<![\d.])(\d+(?:\.\d+)?)\s*[:：]\s*(\d+(?:\.\d+)?)(?![\d.])',text)
    if not match:return None
    mats=[]
    for m in mentions:
        if m['id'] in ('dcm','methanol','ethanol','tert_butanol','water','pbs'):
            if m['id'] not in mats:mats.append(m['id'])
    if len(mats)!=2:return None
    if not re.search(r'mix|mixture|vol|v/v|:|：|混合',text,re.I):return None
    x,y=float(match[1]),float(match[2])
    if x+y<=0:return None
    return {'fractions':{mats[0]:x/(x+y),mats[1]:y/(x+y)},'ratio':match[0],'materials':mats}
def mixture_checks(reference,candidate,ref_conc,cand_conc,mention_fn,method):
    r=ratio_fields(reference,mention_fn(reference,method));c=ratio_fields(candidate,mention_fn(candidate,method))
    # A complete binary percent list is normalized together (66:33 = 2:1),
    # rather than assigning an arbitrary tolerance to every concentration.
    if r is None and len(ref_conc)==2 and 98<=sum(ref_conc.values())<=102:
        total=sum(ref_conc.values());r={'fractions':{k:v/total for k,v in ref_conc.items()},'ratio':'normalized_reference_percent_composition'}
    if c is None:return {}
    if not r or set(r['fractions'])!=set(c['fractions']):return {}
    return {k:('PASS' if abs(r['fractions'][k]-c['fractions'][k])<=1e-6 else 'FAIL') for k in r['fractions']}
def unknown_reason(reference,candidate,field):
    if field=='agitation':
        c=agitation(candidate)
        return 'CANDIDATE_OMITS_CONDITION' if not c['positive'] and not c['negative'] else 'CONDITION_AMBIGUOUS'
    marker={'duration':r'\d.*(?:h|hour|min|day|小时|天)|overnight|until|过夜|直至',
            'temperature':r'RT|room temperature|°|℃|室温|\d\s*C',
            'concentration':r'%|[:：]\s*\d'}.get(field,r'.')
    return 'CANDIDATE_OMITS_CONDITION' if not re.search(marker,candidate,re.I) else 'UNRESOLVED_SEMANTICS_OR_BINDING'
