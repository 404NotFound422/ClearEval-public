"""Apply the user's 2026-11-03 rule: PBS preservation is not scored."""
import re
from . import scoring as previous

VERSION='cleareval-correctness-20261103-v5'
RULE=dict(id='pbs_preservative_not_scored',source='user_message_2026-11-03',
          instruction='PBS防腐不是扣分项',scope='sodium_azide_additive_in_PBS_wash',
          treatment='excluded_from_correctness_and_effectiveness_scoring')
FIELD='concentration:literal:sodium_azide'
AUDIT_FIELD='non_scoring:pbs_preservative:sodium_azide'

def applies(rs,cs):
    return all(re.search(r'\bPBS\b',s['text'],re.I) for s in [rs,cs]) and bool(
        re.search(r'\b(?:wash\w*|rins\w*)\b|清洗|漂洗|洗涤',rs['text'],re.I))

def install():
    e=previous.policy.engine
    previous.resolution.install(e);previous.robustness.install(e);previous.preparation.install(e)
    if getattr(e,'non_scoring_condition_version',None)==VERSION:return
    original=e.checks
    def checks(rs,cs,rg,cg,method,**kw):
        ck=original(rs,cs,rg,cg,method,**kw)
        if FIELD in ck and applies(rs,cs):ck[AUDIT_FIELD]=ck.pop(FIELD)
        return ck
    e.checks=checks;e.non_scoring_condition_version=VERSION

def score_branch(case):
    install();packet=previous.score_branch(case)
    packet.update(version=VERSION,non_scoring_rules=[RULE])
    for mode in ['written','occurrence']:
        for pair in packet[mode]['pairs']:
            other=pair['effectiveness_reference_checks']
            if AUDIT_FIELD in other:
                pair.setdefault('non_scoring_checks',{})[FIELD]=dict(observed_comparison=other.pop(AUDIT_FIELD),rule=RULE['id'])
    return packet
