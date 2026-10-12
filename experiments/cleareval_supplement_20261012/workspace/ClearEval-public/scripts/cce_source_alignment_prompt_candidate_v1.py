"""Single development intervention: anchor parameter comparisons to supplied evidence.

The original rubric, decoder order, source schema, parsing, formula and transport
are unchanged. No desired score or case-specific parameter is supplied here.
"""
import cce_representation_prompt_candidate_v3 as base

CANDIDATE_VERSION = 'parameter-reference-alignment-v1-on-format-display-v3'
NOTE = '''[PARAMETER COMPARISON SOURCE ALIGNMENT]
For co_param, support each numerical comparison in reasoning with the candidate value and its original source unit, and the applicable supplied reference_id/step_id and reference value. Use numerical reference values only from supplied evidence matching method, sample class, and operation phase. Identify any unsourced general experience as unverified rather than presenting it as a supplied reference fact. Do not invent reference durations, transfer a duration between phases, or treat an answer-source citation as a citation for an external standard.
Distinguish an author-procedure mismatch from a demonstrated physical violation. Apply the original 0/1/2 rubric and existing uncertainty contract without extending its categories. A match in one parameter does not establish correctness of the entire protocol. Do not infer that absent reference detail is a wrong answer parameter. Put reference anchors in the free-text reasoning; score_evidence.u must continue to use only the original allowed answer Unit IDs.
'''

def __getattr__(name): return getattr(base, name)
def schema_for_document(doc): return base.schema_for_document(doc)
def make_prompt(case, doc): return base.make_prompt(case, doc)+'\n'+NOTE
def payload_for(prompt, spec, public): return base.payload_for(prompt, spec, public)
