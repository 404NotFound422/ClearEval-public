"""Qualitative Correctness candidate on the tested full canonical source path.

The complete source, canonical map, references, schema and generation options
are inherited from the canonical control. Only the declared judging-scope blocks
change; no model request is performed here.
"""
import cce_canonical_source_candidate_v1 as canonical
import cce_qualitative_correctness_candidate_v1 as qualitative

CANDIDATE_VERSION='canonical-qualitative-correctness-v1'


def __getattr__(name):
    return getattr(canonical,name)


def make_prompt(case,doc):
    original=canonical.make_prompt(case,doc)
    updated=qualitative.replace_block(original,'[UNCERTAINTY CONTRACT]','[QUESTION]',qualitative.UNCERTAINTY)
    updated=qualitative.replace_block(updated,'2.3 参数范围物理合理性 (co_param, 0–2分)',
        '2.4 化学安全性 (co_chem, 0–1分)',qualitative.PARAMETER)
    old_alignment=canonical.base.NOTE
    if updated.count(old_alignment)!=1:
        raise ValueError('Expected one obsolete numerical comparison instruction')
    updated=updated.replace(old_alignment,'')
    return updated+'\n'+qualitative.LABEL_NOTE


def schema_for_document(doc):
    return canonical.schema_for_document(doc)


def payload_for(prompt,spec,public):
    return canonical.payload_for(prompt,spec,public)
