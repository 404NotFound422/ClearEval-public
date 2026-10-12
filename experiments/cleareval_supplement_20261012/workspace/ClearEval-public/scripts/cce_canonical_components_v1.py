"""Apply the frozen v7 primary processor to the canonical source; keep raw SR/SP."""
import cce_posthoc_components_v7 as previous
import cce_canonical_source_candidate_v1 as source


def independent_processing(raw, doc, case, step):
    evaluated = source.evaluation_case(case)
    if doc != source.evaluation_document(case):
        raise ValueError('CANONICAL_PROCESSING_SOURCE_MISMATCH')
    # step remains the score of the edited ORIGINAL full text, not the view.
    result = previous.independent_processing(raw, doc, evaluated, step)
    mapping = source.source_mapping(case, doc)
    spans = source.map_resolved_spans(result, mapping, doc)
    result['canonical_source_provenance_v1'] = {
        'source_mapping': mapping,
        'resolved_citations_to_original': spans,
        'original_step_answer_sha256': step['answer_sha256'],
        'original_step_SR': step.get('sr'), 'original_step_SP': step.get('sp'),
        'primary_scoring_module': previous.scoring.VERSION,
        'no_numeric_score_override': True,
    }
    return result
