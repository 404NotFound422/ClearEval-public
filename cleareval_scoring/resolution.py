"""Resolve evidence already in the answer, without editing it or filling missing facts.

Installed on the isolated experiment engine; no answer IDs or scores enter rules.
Every relaxed notation has a restricted chemical/linguistic domain.
"""
import copy,re

VERSION='evidence-resolution-20261102-v2'
SOURCES={
 'triethanolamine_alias':'https://www.sigmaaldrich.com/US/en/product/sial/t58300',
 'binary_66_34':'https://bio-protocol.org/en/bpdetail?id=4948&type=0',
 'binary_66_33':'https://idisco.info/idisco-protocol/',
 'recipe_facts':'verified_bio_benchmark_20261102_v3/recipe_catalog.json',
 'seedb_batch':'https://bio-protocol.org/en/bpdetail?id=3046&type=0',
}

def typography(text):
    return re.sub('[\u2010-\u2015]','-',text).replace('（','(').replace('）',')')

def install(e):
    if getattr(e,'evidence_resolution_version',None)==VERSION:return
    e.evidence_resolution_version=VERSION
    r=e.recipes
    r.INGREDIENTS.update({
      'triethanolamine':r'triethanolamine|三乙醇胺|2,2[\u2032\']?,2[\u2033\u2032\']{1,2}[-\s]*nitrilotriethanol',
      'dimethylformamide':r'(?:N[-,\s]*N[-,\s]*)?dimethylformamide|\bDMF\b',
      'butylethanolamine':r'(?<!di)\bN[-\s]*butylethanolamine\b',
      'peg_methyl_ether':r'PEG[-\s]*MME(?:\s*550)?|poly\(ethylene\s+glycol\)\s+methyl\s+ether',
    })
    old_parse=r.parse_claim
    def parse_claim(text,ingredients=None):
        original=text
        text=typography(text)
        # Formula ingredients and working-stock dilution have different ownership.
        claim=old_parse(text,ingredients)
        ms=r.ingredient_mentions(claim['text'],ingredients);qs=list(r.QUANTITY.finditer(claim['text']))
        fields={}
        for m in ms:
            before=[q for q in qs if q.end()<=m['start'] and m['start']-q.end()<45
                    and not any(x['start']>=q.end() and x['end']<=m['start'] for x in ms if x!=m)]
            assigned=[]
            if before:
                q=before[-1];gap=claim['text'][q.end():m['start']]
                if not re.search(r'[+,;，；]|\b(?:and|with|in)\b',gap,re.I):assigned=[q]
            after=[q for q in qs if q.start()>=m['end'] and q.start()-m['end']<6
                   and re.fullmatch(r'[\s():：=]*',claim['text'][m['end']:q.start()])]
            if after:assigned+=after[:1]
            for q in assigned:
                v=dict(value=float(q[1]),unit=r.unit(q[2]),span=[q.start(),q.end()],literal=q[0])
                if v not in fields.setdefault(m['id'],[]):fields[m['id']].append(v)
        bound={tuple(v['span']) for vs in fields.values() for v in vs}
        unbound=[];stock=[]
        for q in qs:
            if (q.start(),q.end()) in bound:continue
            tail=claim['text'][q.end():]
            if re.match(r'\s*(?:CUBIC[-\s]*(?:R[12+]?|L|RA)|BB[-\s]*PEG|tB[-\s]*PEG|SeeDB2[-\s]*[GS])\b',tail,re.I):
                stock.append(dict(literal=q[0],span=[q.start(),q.end()]));continue
            unbound.append(dict(literal=q[0],span=[q.start(),q.end()]))
        claim.update(fields=fields,unbound_quantities=unbound,stock_quantities=stock,original_line=original)
        return claim
    r.parse_claim=parse_claim
    old_variant=r.check_variant
    def check_variant(recipe,claim):
        result=old_variant(recipe,claim);ck=result['checks'];present=set(claim['mentioned'])
        # A named modern CUBIC-R replaced by the older sugar/urea base is an
        # explicit chemical substitution, not an unspecified antipyrine amount.
        if recipe['name'] in ('cubic_r','cubic_ra') and {'urea','sucrose'}<=present and not ({'antipyrine','nicotinamide','methylnicotinamide'}&present):
            ck['incompatible_base:urea_sucrose']='FAIL'
        if recipe['components'].get('dmso',{}).get('unit')=='carrier' and 'dmso' not in present:
            if re.search(r'\bin\s+(?:distilled\s+|deionized\s+|d)?water\b|溶[于於]水',claim['text'],re.I):
                ck['carrier_identity']='FAIL'
        result['status']=e.combine(list(ck.values()));return result
    r.check_variant=check_variant
    old_seedb=r.extensions.check_seedb
    def check_seedb(name,claim):
        ck=old_seedb(name,claim)
        if name=='seedb2s' and 'tris_edta' not in claim['mentioned'] and re.search(r'\bin\s+(?:distilled\s+)?water\b',claim['text'],re.I):
            ck['buffer_identity']='FAIL'
        return ck
    r.extensions.check_seedb=check_seedb
    old_cf=e.concentration_fields
    def concentration_fields(text,method):
        t=typography(text);out=old_cf(t,method)
        for m in e.op.mentions(t,method):
            q=re.match(r'\s*\(\s*(\d+(?:\.\d+)?)\s*%',t[m['end']:])
            if q:out[m['id']]=float(q[1])
        return out
    e.concentration_fields=concentration_fields
    old_headings=e.restore_headings
    def restore_headings(case):
        c=old_headings(case);head='';heads={}
        for line in c.get('answer','').splitlines():
            s=re.sub(r'^\s*#{1,6}\s*','',line.strip()).replace('**','').strip()
            numbered=re.match(r'^(\d+\.\d+)\s+',s)
            title=re.match(r'^\d+[.\s、]+\s*([^\d].*)',s)
            if numbered:heads[numbered[1]]=head
            elif title:head=title[1].strip()
        previous_media=set()
        for s in c['candidate_steps']:
            if not s.get('heading') and heads.get(s['id']):
                s['heading']=heads[s['id']];s['heading_origin']='original_markdown_section'
            s['_prior_execution_media']=sorted(previous_media)
            if not re.match(r'\s*(?:if\b|optional\b|若|可选)',s['text'],re.I):
                previous_media.update(e.op.typed_operation(s['text'],s.get('heading',''),c['method'])['primary_materials'])
        return c
    e.restore_headings=restore_headings
    old_features=e.features
    def features(steps,method):
        graph=old_features(steps,method)
        for s,g in zip(steps,graph):
            n=e.representation(s,method)['typed']
            if not g['features']['action'] and n.get('action_origin') in ('medium_in_execution_section','numbered_medium_contact_with_explicit_duration'):
                g['features']['action']=n['action'];g['features']['action_origin']=n['action_origin']
        return graph
    e.features=features
    old_checks=e.checks
    def checks(rs,cs,rg,cg,method,**kw):
        ck=old_checks(rs,cs,rg,cg,method,**kw)
        ca=e.concentration_fields(rs['text'],method);cb=e.concentration_fields(cs['text'],method)
        text=typography(cs['text']);materials=set(cg['features']['primary_materials'])
        if re.search(r'dehydrat|脱水',rs['text'],re.I) and re.search(r'decolori[sz]|bleach|脱色|漂白',text,re.I) and not re.search(r'dehydrat|脱水',text,re.I):
            ck['action']='FAIL'
        if ck.get('execution_branch')=='UNKNOWN' and re.search(r'until\s+(?:clear|transparent)',rs['text'],re.I):
            endpoint=re.search(r'(?:若|if).*?(?:不清晰|仍.*散射|not.*(?:clear|transparent))',text,re.I)
            continuation=re.search(r'再孵育|reincubat|incubat.*again',text,re.I)
            if endpoint and continuation and materials and materials<=set(cs.get('_prior_execution_media',[])):
                ck['execution_branch']='PASS'
        # Explicit volume prose: order is significant, unlike a bag of reagents.
        quantities={}
        for m in e.op.mentions(text,method):
            q=re.search(r'(\d+(?:\.\d+)?)\s*volumes?\s*(?:of\s*)?$',text[max(0,m['start']-30):m['start']],re.I)
            if q:quantities[m['id']]=float(q[1])
        if set(quantities)=={'dcm','methanol'} and set(ca)>={'dcm','methanol'}:
            ratio=quantities['dcm']/quantities['methanol'];expected=ca['dcm']/ca['methanol']
            state='PASS' if abs(ratio-expected)<1e-8 else 'FAIL'
            ck.update({'concentration:dcm':state,'concentration:methanol':state})
        # A restricted nominal-protocol notation equivalence, not a global
        # concentration tolerance: 66 DCM / 33 MeOH versus 66 DCM in MeOH.
        elif materials=={'dcm','methanol'} and ca.get('dcm')==66 and ca.get('methanol')==33 and cb.get('dcm')==66 and 'methanol' not in cb:
            if re.search(r'\bin\s+(?:methanol|MeOH)\b|DCM\s*/\s*(?:methanol|MeOH)',text,re.I) and not re.search(r'\bwater\b|H2O|PBS|水|wt|w/v|w/w',text,re.I):
                ck['concentration:methanol']='PASS'
        # In an execution instruction a single named solvent, with no solution,
        # diluent or stock qualifier, denotes the neat reagent. This does not
        # assert analytical purity and never applies to dissolved solutes.
        if materials=={'dcm'} and ca.get('dcm')==100 and 'dcm' not in cb:
            if not re.search(r'solution|dilut|mixture|\bin\s+(?:water|methanol|PBS)|溶液|稀释|混合|水',text,re.I):
                ck['concentration:dcm']='PASS'
        return ck
    e.checks=checks
