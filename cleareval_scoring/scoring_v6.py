"""Candidate scorer: operation-owned stock claims and exact stock names."""
from copy import deepcopy
from . import scoring_v5,adjudication,operation_claims,policy,recipe_scope

VERSION='cleareval-correctness-20261105-v6.2'
FIELD='declared_recipe:independent_claim'

def _owner(audit):
    variants=[v for c in audit.get('claims',[]) if c['status']=='FAIL' for v in c['variants']]
    # An ingredient mismatch must hold across every alternative to own the
    # deduction; otherwise the quantified composition owns it.
    return 'co_method' if variants and all(any((k.startswith(('extra:','incompatible_base:')) or
               k in {'carrier_identity','buffer_identity','declared_stock_identity'}) and state=='FAIL'
               for k,state in v['checks'].items()) for v in variants) else 'co_param'


def _bind_scoped_checks(packet,audits):
    for a in audits:
        legacy=packet.get('correctness_recipe_audit',{}).get(a.get('stock_name'),{})
        if a.get('scoped_recipe_check') and not a.get('definition_inventory_present') and legacy.get('claims') and legacy.get('status')!='NOT_APPLICABLE':
            # Keep evidence already extracted by the legacy parser until its
            # declaration can be owned; failure to parse is not a pass.
            a['scoped_recipe_check']=False
            a['reason']='LEGACY_CLAIM_RETAINED_PENDING_BINDING'
    by_id={a['candidate']:a for a in audits}
    for mode in ['written','occurrence']:
        for pair in packet[mode]['pairs']:
            a=by_id.get(pair['candidate'])
            if not a or a.get('human_review_id'):continue
            if a.get('scoped_recipe_check'):
                # Replace the older whole-answer result, including stale
                # failures from another use of the same stock.
                pair['correctness_checks'].pop('declared_recipe:'+a['stock_name'],None)
            if a.get('claims'):
                pair['correctness_checks'][FIELD]=a['status']
    scoped=[a for a in audits if a.get('scoped_recipe_check')]
    scoped_ids={a['candidate'] for a in scoped}
    for f in packet.get('formulation_results',[]):
        f['used_by']=[cid for cid in f['used_by'] if cid not in scoped_ids]
    for a in scoped:
        packet['formulation_results'].append(dict(name=a['stock_name'],
            status=a['status'] if a.get('claims') or a.get('human_review_id') else 'NOT_APPLICABLE',
            used_by=[a['candidate']],scope='operation',owner=_owner(a)))
    for name in {a['stock_name'] for a in scoped}:
        owned=[a for a in scoped if a['stock_name']==name]
        old=packet['correctness_recipe_audit'].get(name,{})
        per_use=[dict(candidate=a['candidate'],status=a['status'] if a.get('claims') or
                      a.get('human_review_id') else 'NOT_APPLICABLE') for a in owned]
        # Legacy aliases outside this module keep their original evaluation.
        remaining=any(f['name']==name and f['used_by'] and f.get('scope')!='operation'
                      for f in packet['formulation_results'])
        if remaining:
            old.update(scope='mixed_legacy_and_operation',per_use=per_use)
        else:
            active=[u['status'] for u in per_use if u['status']!='NOT_APPLICABLE']
            packet['correctness_recipe_audit'][name]=dict(status=policy.combine(active) if active else 'NOT_APPLICABLE',
                scope='operation',per_use=per_use,claims=[],property_checks=old.get('property_checks',{}))


def score_branch(case,decisions=()):
    scoring_v5.install()
    execution,count=recipe_scope.project_case(case)
    packet=scoring_v5.score_branch(execution)
    recipe_scope.restore_sources(packet)
    packet=adjudication.apply(packet,case,decisions)
    packet=apply_to_cached_packet(case,packet)
    packet.update(execution_recipe_scope_version=recipe_scope.VERSION,recipe_projected_steps=count)
    return packet


def apply_to_cached_packet(case,packet):
    """Update claims on an adjudicated V5 packet without rerunning alignment.

    Use only for unchanged inputs whose operation matching is unaffected by
    the numeric-name fix. The caller binds the packet to its input snapshot.
    """
    if packet['version']!=scoring_v5.VERSION:
        raise ValueError('Claim patch requires an adjudicated V5 baseline packet')
    packet=deepcopy(packet)
    audits=operation_claims.audit(case,packet)
    findings=[];unresolved=[]
    for a in audits:
        stock=a.get('stock_name')
        reviewed=next((d for d in packet['human_adjudications'] if a['candidate'] in d['candidate_ids']
                       and d['field']=='declared_recipe:'+str(stock)),None)
        if reviewed:
            a.update(machine_status=a['status'],status=reviewed['state'],human_review_id=reviewed['review_id'])
            continue
        if a['status'] not in {'FAIL','UNKNOWN'} or not a.get('claims'):continue
        target=findings if a['status']=='FAIL' else unresolved
        target.append({'candidate':a['candidate'],'stock':a['stock'],'field':FIELD,
                       'owner':_owner(a),'severity':'LOCAL','reason':a['reason'],
                       'source_ids':sorted({v['source_id'] for c in a['claims'] for v in c['variants']})})
    _bind_scoped_checks(packet,audits)
    dilution_audits=recipe_scope.audit_dilutions(case)
    paired={p['candidate'] for p in packet['written']['pairs']}
    for a in dilution_audits:
        # An unknown stock basis in an optional preparation explanation does
        # not invalidate an explicit working concentration. Retain it in the
        # separate preparation audit; only contradictions affect correctness.
        if a['status']=='UNKNOWN':continue
        for mode in ['written','occurrence']:
            for pair in packet[mode]['pairs']:
                step=next(s for s in packet['logical_candidate_steps'] if s['id']==pair['candidate'])
                if step.get('original_id',step['id'])==a['candidate']:
                    pair['correctness_checks'][a['field']]=a['status']
        if a['candidate'] not in paired and a['status'] in {'FAIL','UNKNOWN'}:
            target=findings if a['status']=='FAIL' else unresolved
            target.append(dict(candidate=a['candidate'],field=a['field'],owner='co_param',severity='LOCAL',
                               reason='EXPLICIT_DILUTION_CONSISTENCY',source_span=a['source_span']))
    packet=adjudication.recalculate(packet)
    audits,evidence=operation_claims.compact_audits(audits)
    packet.update(version=VERSION,previous_version=scoring_v5.VERSION,
                  operation_claim_audit=audits,operation_claim_evidence=evidence,
                  independent_recipe_findings=findings,independent_recipe_unresolved=unresolved,
                  preparation_dilution_audit=dilution_audits)
    return packet
