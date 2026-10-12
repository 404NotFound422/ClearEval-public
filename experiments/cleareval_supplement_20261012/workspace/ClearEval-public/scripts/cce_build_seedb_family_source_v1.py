"""Recover fixed-tissue SeeDB2 source branches, with no answer or score reads."""
import copy
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/cce_validation'
OUT = BASE / 'method_family_reference_seedb_v1'
SOURCE = ROOT / 'KnowledgeBase/primary_sources/SEEDB2_PROTOCOL_2018'
CORRECTION = ROOT / 'KnowledgeBase/primary_sources/SEEDB2_CORRECTION_2018'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def save(name, x):
    (OUT / name).write_text(json.dumps(x, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    OUT.mkdir(exist_ok=True)
    snapshots = {p.name: read(p / 'snapshot.json') for p in [SOURCE, CORRECTION]}
    protected = {str(p / name): sha(p / name) for p in [SOURCE, CORRECTION]
                 for name in ['raw.pdf', 'body.txt', 'snapshot.json', 'pdf_fetch.json']}
    for p in [SOURCE, CORRECTION]:
        assert sha(p / 'raw.pdf') == snapshots[p.name]['raw_sha256']
        assert sha(p / 'body.txt') == snapshots[p.name]['text_sha256']
    text = (SOURCE / 'body.txt').read_text(encoding='utf-8')
    correction = (CORRECTION / 'body.txt').read_text(encoding='utf-8')
    c = text.index('C. SeeDB2G (Figure 2)')
    d = text.index('D. SeeDB2S (Figure 2)', c)
    e = text.index('E. Imaging chamber preparation', d)
    f = text.index('F. Anticipated Results', e)
    recipes = text.index('Recipes\n', f)
    acknowledgments = text.index('Acknowledgments', recipes)
    spans = {}

    def span(key, start, end, source=SOURCE):
        body = text if source == SOURCE else correction
        snap = snapshots[source.name]
        pages = [x['page'] for x in snap['page_offsets'] if x['end'] > start and x['start'] < end]
        quote = body[start:end].strip()
        start += len(body[start:end]) - len(body[start:end].lstrip())
        end = start + len(quote)
        record = {'pdf_path': str(source / 'raw.pdf'), 'pdf_sha256': sha(source / 'raw.pdf'),
                  'text_path': str(source / 'body.txt'), 'text_sha256': sha(source / 'body.txt'),
                  'pdf_pages_one_based': pages, 'start': start, 'end': end,
                  'offset_unit': 'Unicode code points in the saved UTF-8 text; end exclusive',
                  'quote': quote, 'quote_sha256': hashlib.sha256(quote.encode('utf-8')).hexdigest()}
        spans[key] = record
        return record

    def between(key, begin, until, start=0):
        a = text.index(begin, start)
        b = text.index(until, a + len(begin))
        return span(key, a, b)

    between('variant_scope', '1. SeeDB2G (RI = 1.46)', 'B. Choice of objective lenses', 0)
    between('objective_scope', 'B. Choice of objective lenses', 'C. SeeDB2G (Figure 2)', 0)
    between('G_wash', '2. Wash the sample', '3. Embed', c)
    between('G_slice', '3. Embed', '4. Transfer', c)
    between('G_permeabilize', '4. Transfer', 'Please cite this article', c)
    between('optional_label', 'Optional: Perform antibody staining', '5. Transfer', c)
    between('G_solution1', '5. Transfer', '6. Transfer', c)
    between('G_solution2', '6. Transfer', '7. Transfer', c)
    between('G_clear', '7. Transfer', 'Notes:', c)
    span('G_storage', text.index('Notes:', c), d)
    between('S_wash', '2. Wash the sample', '3. Embed', d)
    between('S_slice', '3. Embed', '4. Transfer', d)
    between('S_permeabilize', '4. Transfer', '5. Transfer', d)
    between('S_solution1', '5. Transfer', '6. Transfer', d)
    between('S_solution2', '6. Transfer', '7. Transfer', d)
    between('S_Gstage', '7. Transfer', '8. Transfer', d)
    between('S_Sstage', '8. Transfer', '9. Transfer', d)
    between('S_storage', '9. Transfer', 'Figure 2. Graphic protocol', d)
    between('mount_optional_debubble', '1. (Optional)', '2. Cut', e)
    between('mount_chamber_cut', '2. Cut', '3. Remove', e)
    between('mount_chamber_attach', '3. Remove', '4. Leave', e)
    between('mount_sample', '4. Leave', '5. (Optional)', e)
    between('mount_optional_bubbles', '5. (Optional)', '6. Gently', e)
    between('mount_seal', '6. Gently', 'Please cite this article', e)
    between('immersion', '7. Use an appropriate immersion', 'Video 1.', e)
    span('recipes_corrected_current_pdf', recipes, acknowledgments)
    span('formal_correction', correction.index('After official publication'), correction.index('References'), CORRECTION)
    assert '10x Phosphate-buffered saline' in spans['recipes_corrected_current_pdf']['quote']
    assert 'Dilute 10 times' in spans['recipes_corrected_current_pdf']['quote']
    # Definitions are read from the detailed Recipes, not synthesized from figure2.
    recipe_defs = {
        'PBS': 'The cited recipe makes10x PBS; dilute tenfold with water to1x PBS before use, as the formal e3095 correction specifies.',
        'permeabilization': '100 microliters20% saponin solution plus900 microliters PBS.',
        'solution1': '100 microliters20% saponin solution plus333 microliters Omnipaque350 plus567 microliters water.',
        'solution2': '100 microliters20% saponin solution plus500 microliters Omnipaque350 plus400 microliters water.',
        'SeeDB2G_clearing': '2% saponin in Omnipaque350.',
        'SeeDB2G_mounting_selected': 'Use Omnipaque350 directly. The separately reported Histodenz alternative is not mixed into this selected preparation.',
        'SeeDB2S_clearing': '3780 microliters Tris-EDTA buffer(pH7.6) plus420 microliters20% saponin solution plus10g Histodenz; retain original composition without inferring final volume.',
        'SeeDB2S_mounting': '4200 microliters Tris-EDTA buffer(pH7.6) plus10g Histodenz. Add buffer to a50ml tube, then Histodenz, and dissolve fully on a rotator.',
        'Tris_EDTA': '10mM Tris-HCl and0.25mM EDTA, pH7.6. Do not substitute PBS in SeeDB2S preparation.',
    }
    refs = []
    for variant, start in [('G', c), ('S', d)]:
        defs = [
            ('Wash the fixed brain in PBS three times with gentle shaking,10 minutes each.', f'{variant}_wash', 'fixed_sample_wash'),
            ('Embed in4% low-melting-point agarose/PBS in the desired orientation and cut the brain with a vibratome, selecting the author slice branch(200-500 micrometers).', f'{variant}_slice', 'slice_preparation'),
            ('Transfer to the permeabilization solution and incubate with shaking overnight(more than16 hours) at4 degrees C. Any selected antibody/counterstaining is performed before clearing.', f'{variant}_permeabilize', 'permeabilization'),
            ('Transfer the slice to a new tube containing solution1; incubate on a rotator for2-4 hours.', f'{variant}_solution1', 'clearing'),
            ('Transfer the slice to a new tube containing solution2; incubate on a rotator for2-4 hours.', f'{variant}_solution2', 'clearing'),
            ('Transfer the slice to a new tube containing SeeDB2G with saponin; incubate on a rotator for2-4 hours.', 'G_clear' if variant == 'G' else 'S_Gstage', 'clearing_RI'),
        ]
        if variant == 'S':
            defs.append(('Transfer the slice to a new tube containing SeeDB2S with saponin; incubate on a rotator for2-4 hours.', 'S_Sstage', 'clearing_RI'))
            defs.append(('Transfer to a new tube of SeeDB2S without saponin for mounting;0.01% sodium azide may be added for long-term storage.', 'S_storage', 'terminal_medium'))
        else:
            defs.append(('Store in SeeDB2G without saponin until mounting and imaging. The author reports storage in Eppendorf tubes at4 degrees C for up to6 months and specifies0.05% sodium azide for long-term storage.', 'G_storage', 'terminal_medium'))
        defs += [
            ('Cut the silicone rubber sheet to the appropriate imaging-chamber size.', 'mount_chamber_cut', 'preimaging_mounting'),
            ('If present, remove the protection sheets from the0.2mm silicone sheet; press the sheet onto the glass slide and remove air between the sheet and slide.', 'mount_chamber_attach', 'preimaging_mounting'),
            (f'Place a drop of SeeDB2{variant} from the storage tube, not fresh medium, into the chamber and mount the brain slice with a perforated spoon and paintbrush. Do not place the slice on a dry surface.', 'mount_sample', 'preimaging_mounting'),
            (f'Gently press the cover glass onto the chamber and use spillover SeeDB2{variant} to seal it. Do not use nail polish.', 'mount_seal', 'preimaging_mounting'),
            (('Use glycerol immersion medium(RI1.46) for the selected high-resolution SeeDB2G imaging branch; SeeDB2G itself is not an immersion medium.' if variant == 'G' else 'Use TypeF oil immersion medium(RI1.52) for SeeDB2S; SeeDB2S itself is not an immersion medium.'), 'immersion', 'optical_setup'),
        ]
        steps = []
        for i, (prose, key, module) in enumerate(defs, 1):
            s = spans[key]
            steps.append({'step_id': f'SEEDB2{variant}_2018_FIXED_SLICE_{i:02d}', 'text': prose,
                          'module': module, 'required': True,
                          'required_scope': 'coverage of this selected author branch, not biological necessity confirmation',
                          'source_anchor': f"Bio-protocol e3046 pp{s['pdf_pages_one_based']}; body[{s['start']}:{s['end']})",
                          'source_spans': [s]})
        ref = {'reference_id': f'SEEDB2{variant}_2018_CORRECTED_FIXED_SLICE_COMPLETE_V1',
               'route_id': f'SeeDB2{variant}', 'route_aliases': [f'SeeDB2{variant}', f'SeeDB2-{variant}', f'SeeDB2 {variant}'],
               'method_family_id': 'SeeDB2', 'method_family_aliases': ['SeeDB2'],
               'version_id': f'SEEDB2{variant}_BIOPROTOCOL_2018_WITH_E3095_CORRECTION',
               'protocol_version': f'SeeDB2{variant} fixed mouse brain slice branch, Bio-protocol e3046 with e3095 correction',
               'question_ids': [], 'requires_explicit_task_binding': True, 'active_for_scoring': False,
               'status': 'source_extracted', 'human_confirmation': None, 'formal_eligible': False,
               'family_id': 'KE_IMAI_2018_SEEDB2_BIOPROTOCOL3046',
               'source_path': str(SOURCE / 'raw.pdf'), 'source_sha256': sha(SOURCE / 'raw.pdf'),
               'source_url': 'https://bio-protocol.org/pdf/Bio-protocol3046.pdf', 'doi': '10.21769/BioProtoc.3046',
               'correction': {'doi': '10.21769/BioProtoc.3095', 'path': str(CORRECTION / 'raw.pdf'), 'sha256': sha(CORRECTION / 'raw.pdf')},
               'steps': steps, 'reagent_definitions': recipe_defs,
               'reagent_definition_source_spans': [spans['recipes_corrected_current_pdf'], spans['formal_correction']],
               'full_action_scope': {'start': 'Fixed/postfixed mouse brain; initial wash and source-required sectioning remain included.',
                                    'sample': 'Author200-500 micrometer slice workflow; SeeDB2S separately recommends relatively thin slices below300 micrometers for its high-NA optics.',
                                    'end': 'Complete clearing/RI, terminal medium, chamber mounting and appropriate optical immersion setting.',
                                    'excluded': ['Initial perfusion/fixation already completed at this scope start', 'Optional antibody/counterstaining procedure', 'Optional bubble-removal branches', 'Image acquisition/analysis', 'Any vector engineering, expression or delivery procedure'],
                                    'no_required_slice_step_removed': True},
               'completeness_status': 'complete_selected_author_fixed_slice_clear_RI_mounting_scope',
               'conditional_labeling': {'required_by_all_cases': False, 'source_calls_antibody_branch_optional': True,
                                       'if_requested': 'Perform before clearing; the source reports antibody penetration only200-300 micrometers, not3mm.'},
               'continuous_conditions': ['Do not store samples in saponin-containing solutions.', 'Prolonged saponin incubation above24 hours can damage thin slices or neonatal samples.', 'Do not expose SeeDB2S solution or its cleared specimens to air for longer than5 minutes.'],
               'optional_actions_source_spans': [spans['mount_optional_debubble'], spans['mount_optional_bubbles']],
               'unknowns': ['Exact clearing-stage temperature not explicitly supplied in local numbered incubations; no room-temperature value imputed.',
                            'No complete independently specified3mm intact-block branch is recovered here.',
                            'Task-specific marker combination, six-month weak dual-signal outcome and full3mm imaging depth are not validated by this reference.',
                            'G storage recommendation0.05% azide and S/generic recipe0.01% are retained as separate source statements, not silently averaged.'],
               'version_rule': 'Explicit SeeDB2G or SeeDB2S restricts that branch. Generic SeeDB2 may compare versions only after source-defined sample and optical scope is compatible; no matching solely by family name.',
               'true_multiversion_group': 'SEEDB2_2018_FIXED_SLICE_CLEAR_RI_MOUNTING',
               'not_an_independent_source_family': True}
        refs.append(ref)
    save('candidate_references.json', {'schema': 'seedb2-source-only-author-branches-v1', 'active_for_scoring': False, 'references': refs})
    save('source_passages.json', spans)
    gap = {
        'status': 'complete_slice_sources_recovered_task_binding_pending',
        'whole_mount_lead': {'variant': 'SeeDB2G', 'source': 'C5-C7 explicitly give6-10 hours for whole-mount samples.',
                            'preparation_gap': 'C3 nevertheless instructs agarose embedding and vibratome cutting; a complete separately specified3mm intact-block preparation branch is not established by this source.',
                            'not_claimed': 'This does not prove SeeDB2G cannot clear3mm or larger tissue. It limits the recovered complete comparable reference.',
                            'source_spans': [spans['G_slice'], spans['G_solution1'], spans['G_solution2'], spans['G_clear']]},
        'slice_branch': {'SeeDB2G': '200-500micrometer authored incubation branch', 'SeeDB2S': '200-500micrometer procedural range; below300micrometer recommendation for the high-NA oil objective context'},
        'current_3mm_binding': 'not_activated; do not delete the sectioning operation or substitute slice timings merely to score the existing NA cases',
        'complete_unsectioned_reference_needed': 'An author-supported complete whole-mount/3mm preparation-to-clearing/RI branch, with version and scope, or confirmation of a source-specific branch; not inferred from a duration line alone.',
        'source_family_matching': 'SeeDB2 umbrella is metadata only; G/S and required sample preparation remain distinct. Explicit branch names and scope take priority over maxSR.',
        'formal_eligible': False, 'expert_confirmation': None, 'question_ids_bound': [],
        'new_model_requests': 0, 'answer_scores_read': 0, 'heldout_scientific_outputs_read': 0}
    save('scope_gap.json', gap)
    save('source_manifest.json', {'sources': [{'source_id': name, 'snapshot': snapshots[name]} for name in snapshots],
        'input_sha256': protected, 'recipe_correction_applied': True,
        'local_protocol_pdf_already_contains_PBS_correction': True,
        'formal_correction_is_not_counted_as_an_alternative_protocol': True,
        'detailed_recipe_selected_over_graphic_schematic': True,
        'recipe_figure_note': 'Figure2 is schematic and reports rounded/differently expressed SeeDB2S composition; detailed Recipes are preserved without inventing equivalence.',
        'actual_visual_pages': {'protocol': [5, 6, 7, 12], 'correction': [1]},
        'new_network_requests': 0, 'new_model_requests': 0})
    for s in spans.values():
        t = Path(s['text_path']).read_text(encoding='utf-8')
        assert t[s['start']:s['end']] == s['quote']
        assert hashlib.sha256(s['quote'].encode('utf-8')).hexdigest() == s['quote_sha256']
    assert [len(r['steps']) for r in refs] == [12, 13]
    assert all(not r['question_ids'] for r in refs)
    assert all(sha(p) == h for p, h in protected.items())
    save('construction_record.json', {'status': 'source_extracted_complete_for_stated_slice_scope',
        'source_family_count': 1, 'author_variants': 2, 'complete_task_bound_references': 0,
        'expert_confirmations': 0, 'local5_plus15_budget_consumed': 0, 'source_recovery_work_recorded_separately': True,
        'old_sources_modified': False, 'new_scoring': False, 'new_model_requests': 0,
        'raw_answers_read': 0, 'scores_read': 0, 'heldout_scientific_outputs_read': 0})
    save('build_run.json', {'status': 'success', 'utc': datetime.now(timezone.utc).isoformat(),
        'actual_command': [sys.executable, 'scripts/cce_build_seedb_family_source_v1.py'],
        'script_sha256': sha(__file__), 'candidate_sha256': sha(OUT / 'candidate_references.json'),
        'source_spans_verified': len(spans), 'all_old_source_hashes_unchanged': True,
        'step_counts': [12, 13], 'active_question_count': 0, 'new_model_requests': 0, 'new_network_requests': 0})
    print(json.dumps({'status': 'success', 'candidate_sha256': sha(OUT / 'candidate_references.json'),
                      'source_spans': len(spans), 'step_counts': [12, 13], 'active_question_count': 0,
                      'new_model_requests': 0, 'new_network_requests': 0}))


if __name__ == '__main__':
    main()
