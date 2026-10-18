"""Posthoc exact-text adapter to existing benchmark proxy rules, not science truth."""
import re, hashlib

def restore(question, manifest, original, runner, time_rows):
    assert hashlib.sha256(question.encode()).hexdigest()==manifest['question_sha256']
    facts=manifest['facts']
    for f in facts:assert question[f['start']:f['end']]==f['quote']
    identity=facts[0]['quote'];dimension=' '.join(f['quote'] for f in facts[1:])
    out=original.copy();audit={'identity':identity,'dimensions':dimension,'question_sha256':manifest['question_sha256'],'facts':facts,'source':manifest['question_source'],'scientific_certified':False,'status':'POSTHOC_EXISTING_UNCALIBRATED_PROXY','ri_decision':'PRESERVE_ARCHIVED','tier_decision':'PRESERVE_ARCHIVED'}
    tumor=bool(re.search('瘤|癌|肿瘤',identity))
    if not out.get('tissue_ri_value'):
        if tumor:audit['ri_decision']='REJECT_TUMOR_ALIAS_OR_REFERENCE_UNVERIFIED'
        else:
            ref=runner._resolve_tissue_ri_reference(identity)
            if ref['resolved_key'] is not None:
                out.update(tissue_ri_value=ref['value'],tissue_ri_reference=ref)
                audit['ri_decision']='EXISTING_LITERAL_KEYWORD_TABLE_REFERENCE'
                audit['ri_reference']=ref
            else:audit['ri_decision']='REJECT_UNKNOWN_IDENTITY_NO_DEFAULT_BACKFILL'
    if not out.get('tissue_tier_code'):
        tier=None
        if tumor:audit['tier_decision']='REJECT_TUMOR_NOT_WHOLE_BRAIN'
        elif not dimension:audit['tier_decision']='REJECT_MISSING_DIMENSIONS'
        else:
            # Parse only explicit length ranges or three-axis dimensions.
            # Units and both range bounds are semantic evidence, not decorations.
            n=r'(\d+(?:\.\d+)?)'
            length=re.fullmatch(r'\s*长度约\s*'+n+r'\s*(?:[–-]\s*'+n+r'\s*)?(mm|cm)(?:，管径约\s*'+n+r'\s*(?:[–-]\s*'+n+r'\s*)?(mm|cm))?\s*',dimension)
            axes=re.fullmatch(r'\s*(?:大小)?约\s*'+n+r'\s*(mm|cm)\s*[×x]\s*'+n+r'\s*(mm|cm)\s*[×x]\s*'+n+r'\s*(mm|cm)\s*',dimension)
            extent=[]
            if length:
                lo,hi,unit=length.group(1,2,3)
                factor=10 if unit=='cm' else 1
                lower,upper=float(lo)*factor,float(hi or lo)*factor
                if 0<lower<=upper:extent=[lower,upper]
            elif axes:
                vals=[float(axes.group(i))*(10 if axes.group(i+1)=='cm' else 1) for i in (1,3,5)]
                if all(v>0 for v in vals):extent=[max(vals),max(vals)]
            if extent and extent[0]>=15 and extent[1]<=80 and re.search('脊髓|结肠',identity):tier='T06_LONG_CNS_OR_TUBULAR_15_80MM'
            elif extent and 5<=extent[0]<=extent[1]<=20 and '小鼠' in identity and '胰腺' in identity:tier='T05_MOUSE_SOFT_ORGAN_5_20MM'
            if tier:
                out['tissue_tier_code']=tier
                audit.update(tier_decision='EXISTING_EXPLICIT_GEOMETRY_CATEGORY_PROXY',extent_mm=extent,tier_code=tier)
                audit['matching_existing_kb_rows']=[r for r in time_rows if r['tier_code']==tier]
            else:audit['tier_decision']='REJECT_NO_UNIQUE_EXISTING_GEOMETRY_CATEGORY'
    out['archived_metadata_restoration']=audit
    return out,audit
