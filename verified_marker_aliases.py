"""Evidence-backed identities used only for marker-to-target recognition.

A clone recognizing an epitope is not a claim that its full staining protocol,
secondary antibody, spectral compatibility, or tissue clearing is valid.
"""
import re

IDENTITY_VERSION = 'marker-target-identities-2026-09-22-v1'
IDENTITY_EVIDENCE = [{
    'target': 'PNAd',
    'clone': 'MECA-79',
    'relation': 'antibody recognizes PNAd-associated sulfated carbohydrate epitope',
    'species_scope': ['human', 'mouse'],
    'source': 'Thermo Fisher Scientific product certificate, catalog 53-6036-80',
    'url': 'https://assets.thermofisher.com/TFS-Assets/LSG/certificate/Certificates-of-Analysis/53603680_2285015.PDF',
    'verified_date': '2026-09-22',
    'limitation': 'Target-recognition mapping only; not an antibody-isotype or compatibility equivalence.',
}]

# These normalized forms follow the existing name normalization in the scorer.
# Generic HEV, endothelium, CD31, and other MECA clones are deliberately absent.
TARGET_ALIASES = {
    'pnad': ['pnad', 'meca79', 'peripheralnodeaddressin', 'peripherallymphnodeaddressin'],
    'meca79': ['meca79', 'pnad', 'peripheralnodeaddressin', 'peripherallymphnodeaddressin'],
}


def verified_target_identity(name):
    """Recognize a whole clone/target token, not a partial clone number."""
    if not isinstance(name, str):
        return None
    if re.search(r'(?<![a-z0-9])(?:meca[\s_\-\u2010-\u2015]*79|pnad)(?![a-z0-9])', name, re.IGNORECASE):
        return 'pnad'
    if re.search(r'\bperipheral\s+(?:lymph\s+)?node\s+addressin\b', name, re.IGNORECASE):
        return 'pnad'
    return None


def same_verified_target(left, right):
    identity = verified_target_identity(left)
    return identity is not None and identity == verified_target_identity(right)
