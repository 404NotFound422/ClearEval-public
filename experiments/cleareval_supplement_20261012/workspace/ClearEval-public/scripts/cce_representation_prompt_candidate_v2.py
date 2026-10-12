"""Formatting-only display candidate; original document and evidence IDs remain authoritative.

No model-call entry point. This candidate adds a mapped reading aid to the exact
order-only v11 generation prompt. It does not replace the source, edit scores,
change the decoder, or install the normalized SR/SP diagnostic as the main score.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT)]
import cce_generation_order_only_v1 as base
import cce_representation_repair_v2 as representation
original=base.original
VERSION=original.VERSION
CANDIDATE_VERSION='source-preserving-format-display-v2-positive-prefix-grammar'
OUT=representation.OUT/'prompt_candidate_v2'
NOTE='''[SOURCE-PRESERVING READING AID v2]
The following view repeats the complete answer after removal of recognized structural list prefixes with explicit action/title syntax and whitespace normalization. It separates adjacent action sentences for reading. It adds no scientific facts, parameter values, operations, relationships, precedence or reference requirements. Its rows are not new evidence IDs and do not define the number of scientific steps. The original full source, original Unit/typed IDs, complete-name occurrence rules and original rubric above remain authoritative.
Assess the same reported scientific content with the original rubric: list numbering, bullets and line grouping are not parameter omissions or additional parameters. Check reported values and omissions against the same task/reference context, including the rubric's original degree-of-detail criterion; do not silently turn presentation style into a stricter or looser parameter requirement. This instruction does not prescribe any score, treat unresolved evidence as known, or excuse genuine missing information.
Use the original source and its original IDs for every returned citation. Do not cite view row numbers or compute name occurrences in this view. Consult the original surrounding headings, negation, alternatives and conditions whenever a view boundary is insufficient. Nothing in this view establishes scientific equivalence or protocol validity.
'''

def __getattr__(name):return getattr(original,name)
def schema():return original.schema()
def schema_for_document(doc):return base.schema_for_document(doc)
def document(text,source_id):return original.document(text,source_id)
def source_id_for_case(case):return original.source_id_for_case(case)
def convert(raw,doc):return base.convert(raw,doc)
def payload_for(prompt,spec,public):return base.payload_for(prompt,spec,public)
ordered_json=base.ordered_json
format_order_manifest=base.format_order_manifest

def display_view(doc):
    view=representation.canonicalize_full_text(doc['text'])
    if view['original_answer_sha256']!=doc['answer_sha256']:raise ValueError('ORIGINAL_SOURCE_HASH_MISMATCH')
    rows=[];start=0
    for line in view['evaluation_text'].splitlines(keepends=True):
        end=start+len(line.rstrip('\r\n'));ranges=representation.original_ranges(view,start,end)
        unit_ids=[u['unit_id'] for u in doc['units'] if any(a<u['end'] and b>u['start'] for a,b in ranges)]
        rows.append({'text':line.rstrip('\r\n'),'original_unit_ids':unit_ids,
            'original_character_ranges':ranges})
        start+=len(line)
    return {'candidate_version':CANDIDATE_VERSION,'source_id':doc['source_id'],
        'original_answer_sha256':doc['answer_sha256'],'view_sha256':view['evaluation_view_sha256'],
        'offset_convention':doc['offset_convention'],'rows':rows,
        'removed_structural_prefixes':view['removed_structural_prefixes'],
        'nonformat_content_and_order_exact':view['nonformat_content_and_order_exact']}

def make_prompt(case,doc):
    expected=document(case['model_response'],source_id_for_case(case))
    if doc!=expected:raise ValueError('AUTHORITATIVE_DOCUMENT_MISMATCH')
    return base.make_prompt(case,doc)+'\n'+NOTE+json.dumps(display_view(doc),ensure_ascii=False,separators=(',',':'))+'\n'

def offline_check(out):
    checks=[]
    def check(n,v):
        if not v:raise AssertionError(n)
        checks.append({'name':n,'pass':True})
    doc,wire=original.synthetic_fixture();before=copy.deepcopy(doc)
    view=display_view(doc)
    check('original_document_not_mutated',doc==before)
    check('same_source_id_and_original_hash',view['source_id']==doc['source_id'] and view['original_answer_sha256']==doc['answer_sha256'])
    check('same_decoder_values_and_order',schema_for_document(doc)==base.schema_for_document(doc) and list(schema_for_document(doc)['properties'])==list(base.schema_for_document(doc)['properties']))
    check('same_wire_conversion_exact',convert(original.canonical(wire),doc)==base.convert(original.canonical(wire),doc))
    for row in view['rows']:
        actual=''.join(doc['text'][a:b] for a,b in row['original_character_ranges'])
        check('mapped_row_'+str(len(checks)),''.join(actual.split())==''.join(row['text'].split()))
    public={'model':'SYNTHETIC_LOCAL_ONLY','num_ctx':98304,'max_output_tokens':8192,'temperature':0,'enable_thinking':False}
    spec=schema_for_document(doc)
    check('same_transport_options',payload_for('x',spec,public)==base.payload_for('x',spec,public))
    cases=representation.read(representation.PUBLIC/'cases.json')['cases'];records=[]
    for case in cases:
        d=document(case['model_response'],source_id_for_case(case));d0=copy.deepcopy(d);c0=copy.deepcopy(case)
        old=base.make_prompt(case,d);new=make_prompt(case,d);v=display_view(d)
        check(case['case_id']+'_original_prompt_untouched_prefix',new.startswith(old+'\n'))
        check(case['case_id']+'_source_and_case_unchanged',d==d0 and case==c0)
        # UTF-8 bytes are a deliberately conservative tokenizer-independent bound.
        bounds=len(new.encode('utf8'))+8192
        records.append({'case_id':case['case_id'],'question_id':case['question_id'],
          'answer_sha256':d['answer_sha256'],'source_id':d['source_id'],
          'view_sha256':v['view_sha256'],'original_prompt_sha256':original.rawsha(old),
          'candidate_prompt_sha256':original.rawsha(new),'original_prompt_bytes':len(old.encode('utf8')),
          'candidate_prompt_bytes':len(new.encode('utf8')),'conservative_context_bound_with_output':bounds,
          'configured_context':98304,'fits':bounds<=98304,'display_rows':len(v['rows'])})
        check(case['case_id']+'_context_fits',bounds<=98304)
    out.mkdir(parents=True,exist_ok=True)
    if (out/'software_checks.json').exists():raise ValueError('NEW_OUTPUT_DIRECTORY_REQUIRED')
    def b(p):return representation.binding(p)
    result={'status':'pass','candidate_version':CANDIDATE_VERSION,'checks':checks,
      'public_answers':len(cases),'new_model_calls':0,'new_embeddings':0,
      'original_document_schema_conversion_and_payload_unchanged':True,
      'direct_score_invariance_not_yet_tested':True,'full_prompts_not_expected_byte_equal_across_pairs':True,
      'inputs':[b(__file__),b(base.__file__),b(original.__file__),b(representation.__file__),b(representation.PUBLIC/'cases.json')],
      'actual_command':sys.argv,'contexts':records}
    representation.save(out/'software_checks.json',result)
    representation.save(out/'contexts.json',records)
    (out/'prompt_note.txt').write_text(NOTE,encoding='utf8')
    print(json.dumps({'status':'pass','checks':len(checks),'public_answers':len(cases),'max_context_bound':max(r['conservative_context_bound_with_output'] for r in records),'out':str(out),'new_model_calls':0}))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['self-check']);p.add_argument('--out',type=Path,default=OUT/'software_execution_01');a=p.parse_args();offline_check(a.out)
if __name__=='__main__':main()
