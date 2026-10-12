"""Offline checks of complete public E2 inputs and original-source mapping."""
import argparse, copy, json, sys
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT)]
import cce_canonical_source_candidate_v1 as candidate
import cce_canonical_components_v1 as processor
import cce_round3_runner_v2 as runner

R3 = ROOT / 'artifacts/cce_validation/optimizer_round3_20261011'
PANEL = R3 / 'representation_repair/controlled_panel_v1'
INPUTS = R3 / 'canonical_source_v1/inputs_01'


def main(out):
    cases, steps = runner.checked_cases(INPUTS/'cases.json', INPUTS/'steps.json')
    pairs = runner.j.read(PANEL/'pairs.json')
    public = runner.j.read(R3/'development_source_alignment_01/plan.json')['public_model']
    records = {}; checks = []
    def check(name, ok):
        if not ok:
            raise AssertionError(name)
        checks.append({'name': name, 'pass': True})
    for case in cases:
        cid = case['case_id']; before = copy.deepcopy(case)
        doc = candidate.evaluation_document(case)
        view = candidate.source_mapping(case, doc)
        evaluated = candidate.evaluation_case(case)
        prompt = candidate.make_prompt(case, doc)
        schema = candidate.schema_for_document(doc)
        payload = candidate.payload_for(prompt, schema, public)
        check(cid+'_original_case_intact', case == before)
        check(cid+'_question_references_intact', all(evaluated[k] == case[k] for k in ['specific_question','references']))
        check(cid+'_all_scientific_characters_mapped', all(
            index is not None and case['model_response'][index] == view['evaluation_text'][i]
            for i, index in enumerate(view['canonical_char_to_original_char']) if not view['evaluation_text'][i].isspace()))
        check(cid+'_map_preserves_order', [x for x in view['canonical_char_to_original_char'] if x is not None] ==
            sorted(x for x in view['canonical_char_to_original_char'] if x is not None))
        check(cid+'_normalization_idempotent', candidate.evaluation_case(evaluated)['model_response'] == evaluated['model_response'])
        check(cid+'_source_document_exact', doc == candidate.ground.document(evaluated['model_response'], candidate.ground.source_id_for_case(evaluated)))
        check(cid+'_schema_order_preserved', list(schema['properties']) == ['scores','score_evidence','grounded_extraction'])
        check(cid+'_context_fits', len(prompt.encode('utf8'))+public['max_output_tokens']+256 <= public['num_ctx'])
        spans = candidate.map_resolved_spans({'sample': {**doc, 'start':0, 'end':len(doc['text'])}}, view, doc)
        check(cid+'_full_span_maps_exact_content', ''.join(''.join(case['model_response'][a:b] for a,b in spans[0]['original_character_ranges']).split()) == ''.join(doc['text'].split()))
        # Probe only the new wrapper boundary. The unchanged v7 processor has its
        # own actual-data verification; this stub is not a scientific result.
        stub_result = {'metrics': {'sr': steps[cid]['sr'], 'sp': steps[cid]['sp']}, 'arbitrary_unresolved':None}
        original = processor.previous.independent_processing
        def stub(raw, passed_doc, passed_case, passed_step):
            check(cid+'_processor_uses_matching_full_view', passed_doc == doc and passed_case == evaluated)
            check(cid+'_processor_keeps_original_step', passed_step is steps[cid])
            return copy.deepcopy(stub_result)
        try:
            processor.previous.independent_processing = stub
            result = processor.independent_processing('OFFLINE_STUB_ONLY', doc, case, steps[cid])
        finally:
            processor.previous.independent_processing = original
        result.pop('canonical_source_provenance_v1')
        check(cid+'_no_score_or_unknown_override', result == stub_result)
        records[cid] = {'source_id':doc['source_id'], 'view_sha256':doc['answer_sha256'],
            'prompt_sha256':candidate.ground.rawsha(prompt), 'schema_sha256':runner.j.digest(schema),
            'ordered_payload_sha256':runner.hashlib.sha256(runner.ordered(payload)).hexdigest(),
            'raw_SR':steps[cid]['sr'], 'raw_SP':steps[cid]['sp'],
            'context_bound':len(prompt.encode('utf8'))+public['max_output_tokens']+256}
    paired = []
    for pair in pairs:
        a, b = records[pair['baseline_case_id']], records[pair['variant_case_id']]
        keys = ['source_id','view_sha256','prompt_sha256','schema_sha256','ordered_payload_sha256']
        same = all(a[k] == b[k] for k in keys)
        expected = pair['condition'] in ['numbering','merge']
        check(pair['pair_id']+'_identical_format_or_distinct_deletion', same == expected)
        paired.append({**pair,'same_model_input':same, 'baseline':a,'variant':b})
    out = Path(out)
    runner.save_once(out/'checks.json', {'status':'pass','checks':checks,
        'normalizer_boundary_checks':candidate.representation.software_checks(),
        'answers':len(cases),'format_pairs':6,'distinct_deletion_pairs':3,
        'new_model_calls':0,'new_embeddings':0,'processor_boundary_stub_not_scientific_evidence':True,
        'actual_command':[sys.executable,*sys.argv],
        'bindings':[runner.bind(p) for p in [__file__,candidate.__file__,processor.__file__,runner.__file__,candidate.representation.__file__,INPUTS/'cases.json',INPUTS/'steps.json',PANEL/'pairs.json']]})
    runner.save_once(out/'paired_input_checks.json', paired)
    print(json.dumps({'status':'pass','checks':len(checks),'new_model_calls':0,'out':str(out)}))


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    main(parser.parse_args().out)
