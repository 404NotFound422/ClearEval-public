"""Current machine scorer. Human adjudication is a separate, explicit input."""
from pathlib import Path
import sys

from . import policy, resolution, robustness
from . import preparation

VERSION='cleareval-correctness-20261103-v4'

def score_branch(case,*,separate_preparation=True,verify_preparation=True):
    e=policy.engine;resolution.install(e);robustness.install(e)
    if verify_preparation:preparation.install(e)
    normalized=robustness.normalize_case(case)
    work,prep=preparation.partition(normalized)
    if not separate_preparation:work=normalized
    raw=e.score_branch(work)
    raw['scope_complete']=bool(case['candidate_steps'])
    if case['candidate_steps'] and not work['candidate_steps']:
        index=e.recipes.index_claims(normalized['answer'],case['method'],e.op.mentions)
        raw['recipe_audit']={name:e.recipes.evaluate(name,case['reference_id'],index) for name in raw['recipe_audit']}
    packet=policy.project_packet(raw)
    packet.update(version=VERSION,resolution_version=resolution.VERSION,robustness_version=robustness.VERSION,
        preparation_scope_version=preparation.VERSION,answer_surface_edits=normalized.get('_answer_surface_edits',[]),
        preparation_steps=prep,execution_inventory='reagent_preparation_excluded' if separate_preparation else 'legacy_inventory')
    packet['formulation_scope']='explicit_claims_for_named_stocks_in_reference_inventory'
    if separate_preparation:
        packet['excluded'] += [dict(id=s['id'],reason='reagent_preparation_separate_from_specimen_execution') for s in prep['candidate_steps']]
    packet['formulation_results']=[dict(name=name,status=a['status'],
        used_by=sorted({p['candidate'] for p in packet['written']['pairs'] if 'declared_recipe:'+name in p['checks']}),
        evidence=packet['recipe_audit'][name].get('recipe_evidence',[]) or
                 sorted({v['evidence'] for c in packet['recipe_audit'][name].get('claims',[]) for v in c.get('variants',[])}))
        for name,a in packet['correctness_recipe_audit'].items()]
    return packet
