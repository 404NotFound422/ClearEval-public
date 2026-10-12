"""Source-span step representation/evidence candidate on 21 exposed controls.

Original BioProBench scorer, encoder, threshold and historical data are immutable.
This offline candidate adds original-text offsets, local parameter scope evidence,
textual order and an optional literal-object consistency gate. It does not award
new c_param/Correctness scores, infer chemistry, or read held-out material.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import socket
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_validation as core
import cce_representation_normalization_v1 as previous
import cce_judges as judges

BASE=ROOT/'artifacts/cce_validation'
OLD=BASE/'judges/local_controls_supplement_v2'
E2=BASE/'judges/controls_contract_v2'
OUT=BASE/'optimizer_20261010/step_representation_v1'
THRESHOLDS=[.6,.7,.8]
MODES=['original_biopro_baseline','source_span_surface','source_span_surface_object_gate']
ACTION=re.compile(r'\b(?:incubat\w*|wash\w*|rins\w*|transfer\w*|immerse\w*|place|store\w*|dehydrat\w*|clear\w*|mount\w*|equilibrat\w*|stain\w*|permeabili\w*|block\w*|replace\w*|repeat\w*|add|keep|prepare\w*|image|imaging|soak\w*)\b',re.I)
PARAMETERS=[
 ('temperature_annotation',re.compile(r'\bTemperature\s*:\s*[^,)\n]+',re.I)),
 ('duration_annotation',re.compile(r'\b(?:Time|Duration)\s*:\s*[^)\n]+',re.I)),
 ('duration',re.compile(r'(?<![\w.])(?:\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?)\s*(?:hours?|hrs?|minutes?|mins?|days?|months?)\b',re.I)),
 ('temperature',re.compile(r'(?<![\w.])-?\d+(?:\.\d+)?\s*(?:℃|°\s*C|degrees?\s*C)(?![A-Za-z])',re.I)),
 ('concentration',re.compile(r'(?<![\w.])\d+(?:\.\d+)?\s*%(?:\s*\((?:vol/vol|v/v|wt/vol|w/v)\))?',re.I)),
 ('pH',re.compile(r'\bpH\s*(?:adjusted\s*to\s*|=\s*)?\d+(?:\.\d+)?',re.I)),
 ('refractive_index',re.compile(r'\b(?:RI|Refractive Index)\s*=\s*\d+(?:\.\d+)?',re.I)),
]
CONDITIONS=re.compile(r'\b(?:in the dark|dark|airtight|without shaking|gentle shaking|until imaging|before [^,.()]+|until [^.()]+)\b',re.I)
CACHES=[BASE/'embedding_cache',OLD/'embedding_cache',BASE/'representation_normalization_v1/embedding_cache',
        E2/'embedding_cache',BASE/'judges/local_alternative_development/embedding_cache',
        BASE/'judges/local_alternative_q1_v1/embedding_cache',BASE/'expanded_references_v6/embedding_cache',
        BASE/'expanded_references_v7/embedding_cache',BASE/'method_family_steps_v1/embedding_cache']


def require(ok,why):
    if not ok:raise AssertionError(why)
def read(path):return core.read(path)
def save(name,value):core.write(OUT/name,value)
def bind(path):return {'path':str(Path(path).resolve()),'sha256':core.filehash(path)}
def finite(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def no_network(*args,**kwargs):raise RuntimeError('Step representation optimization forbids network/judge calls')
def record(command,**extra):
    p=OUT/'execution_commands.json';rows=read(p) if p.exists() else []
    rows.append({'utc':judges.now(),'actual_command':[sys.executable,*sys.argv],'cwd':str(ROOT),
                 'command':command,'script_sha256':core.filehash(__file__),'new_judge_requests':0,**extra});core.write(p,rows)
def source_inputs():
    return [Path(__file__),Path(core.__file__),Path(previous.__file__),
        *[OLD/n for n in ['cases.json','pairs.json','references.json','step_results.json','step_config.json']],
        E2/'per_case.json',E2/'paired_results.json',
        BASE/'representation_normalization_v1/summary.json',BASE/'representation_normalization_v1/per_case.json',
        *[BASE/'controls'/n for n in ['edits.json','order_conflict_edits.json','granularity_edits.json']]]


def object_vocabulary(references):
    """Literal identifiers are derived from reference text, never high-score pairs.

    Property/unit abbreviations are excluded a priori. Full chemical aliases are
    not inferred: an unrecognized or ambiguous object leaves the gate undecided.
    """
    found={}
    excluded={'RI','RT','PH','ML','UL','MM','UM','C','K'}
    for ref in references:
        for i,step in enumerate(ref['steps']):
            for m in re.finditer(r'(?<![A-Za-z0-9])[A-Z][A-Z0-9-]{1,10}(?![A-Za-z0-9])',step['text']):
                token=m.group()
                if token in excluded:continue
                found.setdefault(token,[]).append({'reference_id':ref['reference_id'],'step_index':i,
                    'step_id':step.get('step_id'),'text_start':m.start(),'text_end':m.end(),
                    'literal':token,'source_anchor':step.get('source_anchor')})
    return [{'object_id':token,'aliases':[token],'reference_evidence':found[token],
        'status':'literal_reference_identifier_not_external_chemical_ontology'} for token in sorted(found)]


def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    references=read(OLD/'references.json')['references']
    vocab=object_vocabulary(references)
    policy={'version':'source_span_surface_object_evidence_v1','population':'All fixed 21 development control full texts; all 15 original pairs; qids 2,21,22.',
        'selection':'No selection by scores, response or lexical gate success. No holdout/confirmation access.',
        'thresholds':THRESHOLDS,'primary_threshold':.7,'modes':MODES,
        'segmentation':'Inherit original core-selected operation stream and prior English surface boundary regex; add monotonic source-character maps. Headings excluded by core are not silently claimed recovered.',
        'boundary_regex':previous.BOUNDARY.pattern,'action_regex':ACTION.pattern,
        'parameter_regexes':[{'kind':k,'regex':r.pattern} for k,r in PARAMETERS],
        'parameter_binding':'Keep parameter inside original local unit; do not assign it to a different action. Multiple predicate mentions remain explicitly ambiguous.',
        'order':'Preserve source order and explicit temporal words; adjacency is textual evidence, not validated biochemical dependency.',
        'object_registry':vocab,
        'optional_gate':'Exclude a reference-generated comparison only when both units name exactly one recognized literal reference object and the identities differ. Unknown/multiple objects are undecided and not gated. No numeric parameter, version, or answer-quality filter.',
        'score_formula':'Original normalized-embedding cosine, SR=row-max threshold coverage and SP=column-max threshold coverage. Optional gate is a separately named eligibility adaptation; original cosine/matrix and original SR/SP are always retained.',
        'direct_score_boundary':'Evidence attachments for original c_param/co_order/co_method/co_param/co_chem only; do not award or alter scores or scales.',
        'no_variant_repair_preselected':True,'new_judge_requests':0,'formal_eligible':False,'expert_returns':0}
    plan={'created_utc':judges.now(),'policy':policy,'frozen_inputs':[bind(p) for p in source_inputs()],
        'encoder':read(OLD/'step_config.json')['encoder'],'source_references':[{
            'reference_id':r['reference_id'],'source_path':r['source_path'],'source_sha256':r['source_sha256'],
            'source_url':r.get('source_url'),'evidence_manifest_path':r.get('evidence_manifest_path'),
            'status':r['status'],'unknown_parameters':r.get('unknown_parameters'),'applicability':r.get('applicability')}
            for r in references]}
    if (OUT/'plan.json').exists():
        old=read(OUT/'plan.json');require(old['policy']==policy and old['frozen_inputs']==plan['frozen_inputs'],'frozen_candidate_changed_use_new_version')
    else:save('plan.json',plan)
    record('prepare',status='frozen_before_candidate_scoring',object_vocabulary=[x['object_id'] for x in vocab])
    print(json.dumps({'status':'prepared','cases':21,'pairs':15,'objects':[x['object_id'] for x in vocab],'new_judge_requests':0}))


def span(text,start,end):
    return {'start':start,'end':end,'text':text[start:end],'start_utf8_byte':len(text[:start].encode('utf-8')),
            'end_utf8_byte':len(text[:end].encode('utf-8')),'line_1based':text.count('\n',0,start)+1}


def project(text,segments):
    """Align selected non-whitespace characters monotonically to exact input."""
    stream=[];mapping=[]
    for seg in segments:
        cleaned=' '.join(seg['text'].split());start,end=seg['start'],seg['end'];cursor=start
        if stream:stream.append(' ');mapping.append(None)
        for ch in cleaned:
            if ch.isspace():stream.append(' ');mapping.append(None);continue
            found=text.find(ch,cursor,end)
            require(found>=cursor,'core_selected_text_not_source_subsequence')
            stream.append(ch);mapping.append(found);cursor=found+1
    return ''.join(stream),mapping


def runs(positions):
    positions=[p for p in positions if p is not None]
    if not positions:return []
    result=[];start=last=positions[0]
    for p in positions[1:]:
        if p==last+1:last=p
        else:result.append((start,last+1));start=last=p
    result.append((start,last+1));return result


def frame_evidence(fulltext,text,mapping,vocab,unit_id):
    def local_span(a,b):
        pieces=runs(mapping[a:b]);require(pieces,'empty_evidence_span')
        return {'unit_start':a,'unit_end':b,'surface_text':text[a:b],
            'source_envelope':span(fulltext,pieces[0][0],pieces[-1][1]),
            'source_pieces':[span(fulltext,x,y) for x,y in pieces]}
    actions=[{'surface':m.group(),'evidence':local_span(m.start(),m.end())} for m in ACTION.finditer(text)]
    # A leading Before-clause is retained as temporal evidence, not relabelled as
    # the main operation merely because it contains the word imaging.
    boundary=text.find(',')+1 if re.match(r'^Before\b',text,re.I) and ',' in text else 0
    primary=next((a for a in actions if a['evidence']['unit_start']>=boundary),actions[0] if actions else None)
    parameters=[];covered=[]
    for kind,regex in PARAMETERS:
        for m in regex.finditer(text):
            if any(a<=m.start() and b>=m.end() for a,b in covered):continue
            parameters.append({'kind':kind,'value_text':m.group(),'bound_unit_id':unit_id,
                'binding_status':'local_surface_unit_scope_not_semantic_assignment',
                'evidence':local_span(m.start(),m.end())});covered.append((m.start(),m.end()))
    objects=[]
    for obj in vocab:
        for alias in obj['aliases']:
            for m in re.finditer(r'(?<![A-Za-z0-9])'+re.escape(alias)+r'(?![A-Za-z0-9])',text):
                objects.append({'object_id':obj['object_id'],'literal':m.group(),'evidence':local_span(m.start(),m.end())})
    object_ids=sorted({o['object_id'] for o in objects})
    return {'unit_id':unit_id,'text':text,'source_envelope':span(fulltext,min(p for p in mapping if p is not None),max(p for p in mapping if p is not None)+1),
        'source_pieces':[span(fulltext,a,b) for a,b in runs(mapping)],
        'primary_action_surface_candidate':primary,'all_action_word_mentions':actions,
        'atomic_action_validated':False,'multiple_action_mentions_unresolved':len(actions)>1,
        'parameter_evidence':parameters,'literal_object_evidence':objects,'literal_object_ids':object_ids,
        'unique_recognized_object':object_ids[0] if len(object_ids)==1 else None,
        'object_recognition_status':'single_literal' if len(object_ids)==1 else 'multiple_ambiguous' if object_ids else 'unknown',
        'condition_evidence':[{'surface':m.group(),'evidence':local_span(m.start(),m.end())} for m in CONDITIONS.finditer(text)]}


def representation(fulltext,segments,vocab,source_id):
    stream,mapping=project(fulltext,segments)
    old_units,old_stream=previous.normalize(segments)
    require(stream==old_stream,'prior_surface_stream_not_reproduced')
    units=[]
    for i,u in enumerate(old_units):
        a,b=u['normalized_stream_start'],u['normalized_stream_end']
        require(stream[a:b]==u['text'],'unit_slice_not_exact')
        units.append(frame_evidence(fulltext,u['text'],mapping[a:b],vocab,f'{source_id}::unit_{i+1:03d}'))
    # Character preservation check covers the inherited selected operation stream,
    # not text intentionally excluded by the original core segmenter.
    nonws=''.join(ch for ch in stream if not ch.isspace())
    selected=''.join(fulltext[p] for p in mapping if p is not None)
    require(nonws==selected,'source_character_roundtrip')
    edges=[{'from_unit':a['unit_id'],'to_unit':b['unit_id'],'relation':'next_in_text',
            'semantic_precedence_verified':False,'source_order_preserved':a['source_envelope']['end']<=b['source_envelope']['start']}
            for a,b in zip(units,units[1:])]
    require(all(e['source_order_preserved'] for e in edges),'unit_source_order_overlap')
    return {'source_id':source_id,'full_text_sha256':core.digest(fulltext),'selected_stream_sha256':core.digest(stream),
        'selected_nonwhitespace_character_count':len(nonws),'selected_text_and_order_roundtrip':True,
        'omitted_source_content_not_claimed_recovered':True,'original_segment_n':len(segments),'unit_n':len(units),
        'units':units,'textual_order_edges':edges,'semantic_order_validated':False}


class Encoder(core.Encoder):
    def __init__(self):
        super().__init__();self.created={};self.reused={};self.cache=OUT/'embedding_cache';self.cache.mkdir(exist_ok=True)
    def encode(self,texts):
        rows=[]
        for text in texts:
            name=core.digest([self.identity,text])+'.npy';found=[p/name for p in CACHES+[self.cache] if (p/name).exists()]
            if found:
                path=found[0];require(all(core.filehash(p)==core.filehash(path) for p in found),'conflicting_cached_vectors')
                value=self.np.load(path,allow_pickle=False)
                if str(path) not in self.created:self.reused[str(path)]=core.filehash(path)
            else:
                value=self.model.encode([text],normalize_embeddings=True,show_progress_bar=False)[0]
                path=self.cache/name;self.np.save(path,value);self.created[str(path)]=core.filehash(path)
            require(value.shape==(768,) and self.np.isfinite(value).all(),'invalid_embedding_vector');rows.append(value)
        return self.np.asarray(rows)


def matrix_score(matrix,threshold):
    rmax=matrix.max(axis=1);gmax=matrix.max(axis=0)
    return {'sr':float((rmax>=threshold).mean()),'sp':float((gmax>=threshold).mean()),
        'reference_n':int(matrix.shape[0]),'generated_n':int(matrix.shape[1]),
        'reference_hits':int((rmax>=threshold).sum()),'generated_hits':int((gmax>=threshold).sum()),
        'reference_max_similarity':[float(x) for x in rmax],'generated_max_similarity':[float(x) for x in gmax],
        'best_generated_indices':[int(x) for x in matrix.argmax(axis=1)]}


def object_gate(ref_units,answer_units,matrix):
    mask=matrix.copy();excluded=[];unknown=0
    for i,r in enumerate(ref_units):
        for k,a in enumerate(answer_units):
            x,y=r['unique_recognized_object'],a['unique_recognized_object']
            if x is not None and y is not None and x!=y:
                mask[i,k]=-1.
                excluded.append({'reference_index':i,'generated_index':k,'reference_object':x,'generated_object':y,
                    'original_cosine':float(matrix[i,k]),'reason':'different_unique_explicit_reference_object_identifiers',
                    'reference_object_spans':r['literal_object_evidence'],'generated_object_spans':a['literal_object_evidence']})
            elif x is None or y is None:unknown+=1
    return mask,excluded,unknown


def validate_sources(plan):
    for item in plan['frozen_inputs']:require(core.filehash(item['path'])==item['sha256'],'frozen_source_changed:'+item['path'])
    for ref in plan['source_references']:require(core.filehash(ref['source_path'])==ref['source_sha256'],'source_PDF_changed')


def deletion_trace(cases,originals,pairs,old_steps):
    rows=[]
    for pair in pairs:
        if pair['condition']!='necessary_step_deletion':continue
        baseline=cases[pair['baseline_case_id']];variant=cases[pair['variant_case_id']]
        before=old_steps[baseline['case_id']];after=old_steps[variant['case_id']]
        ref=next(r for r in originals if r['reference_id']==before['reference_id'])
        target=[i for i,s in enumerate(ref['steps']) if s.get('module') in ['ri_matching','storage']]
        if not target:target=[i for i,s in enumerate(ref['steps']) if re.search(r'\bDBE\b',s['text'])]
        match_changes=[]
        for i in target:
            a,b=before['matches'][i],after['matches'][i]
            match_changes.append({'reference_index':i,'reference_step_id':ref['steps'][i].get('step_id'),
                'source_anchor':ref['steps'][i].get('source_anchor'),'baseline_max':a['similarity'],'variant_max':b['similarity'],
                'baseline_matched':a['matched'],'variant_matched':b['matched'],
                'baseline_best_generated_index':a['generated_index'],'variant_best_generated_index':b['generated_index'],
                'baseline_generated_text':a['generated_text'],'variant_generated_text':b['generated_text'],
                'already_unmatched_at_baseline':not a['matched']})
        residual=[]
        for m in re.finditer(r'\bDBE\b|\bdibenzyl ether\b|\brefractive index\b|\bRI matching\b',variant['model_response'],re.I):
            containing=next((s for s in after['generated_steps'] if s['start']<=m.start()<s['end']),None)
            residual.append({'match':span(variant['model_response'],m.start(),m.end()),
                'original_segment_index':after['generated_steps'].index(containing) if containing else None,
                'segment_text':containing['text'] if containing else None,
                'residual_mention_is_not_automatically_complete_deleted_operation':True})
        rows.append({'pair_id':pair['pair_id'],'question_id':pair['question_id'],'reference_id':ref['reference_id'],
            'baseline_sr':before['sr'],'variant_sr':after['sr'],'delta_sr':after['sr']-before['sr'],
            'target_reference_rows':match_changes,'residual_full_text_mentions':residual,
            'all_target_rows_already_unmatched_at_baseline':all(x['already_unmatched_at_baseline'] for x in match_changes),
            'direct_explanation':'baseline_target_rows_below_threshold_binary_SR_cannot_fall' if all(x['already_unmatched_at_baseline'] for x in match_changes) else 'at_least_one_baseline_target_match_can_be_lost',
            'variant_invalidity_established':False,'repair_performed':False,
            'limitations':'Residual wording is displayed for review. A remaining pre-imaging equilibration mention alone is not evidence that DBE transfer/storage operations were retained.'})
    return rows


def run():
    socket.create_connection=no_network;socket.socket.connect=no_network;socket.socket.connect_ex=no_network
    plan=read(OUT/'plan.json');validate_sources(plan)
    encoder=Encoder();require(encoder.identity==plan['encoder'],'frozen_encoder_drift')
    cases=read(OLD/'cases.json')['cases'];pairs=read(OLD/'pairs.json');refs=read(OLD/'references.json')['references']
    require(len(cases)==21 and len(pairs)==15,'complete_control_population')
    old_steps={r['case_id']:r['step_result'] for r in read(OLD/'step_results.json')}
    e2={r['case_id']:r for r in read(E2/'per_case.json')}
    vocab=plan['policy']['object_registry'];reference_units={};reference_packets=[]
    for ref in refs:
        strings=[s['text'] for s in ref['steps']];full='\n'.join(strings);offset=0;segments=[];source_ranges=[]
        for i,text in enumerate(strings):
            segments.append({'text':text,'start':offset,'end':offset+len(text)})
            source_ranges.append({'joined_start':offset,'joined_end':offset+len(text),'step_index':i,
                'json_pointer':f"/references/{refs.index(ref)}/steps/{i}/text",'step_id':ref['steps'][i].get('step_id'),
                'source_anchor':ref['steps'][i].get('source_anchor')});offset+=len(text)+1
        rep=representation(full,segments,vocab,ref['reference_id']);reference_units[ref['reference_id']]=rep
        reference_packets.append({**rep,'source_kind':'frozen_reference_reconstruction_text_not_verbatim_author_prose',
            'references_file':bind(OLD/'references.json'),'joined_source_text':full,'joined_source_ranges':source_ranges,
            'author_source_path':ref['source_path'],'author_source_sha256':ref['source_sha256'],
            'author_source_url':ref.get('source_url'),'source_pages':ref.get('source_pages'),
            'evidence_manifest_path':ref.get('evidence_manifest_path'),'unknown_parameters':ref.get('unknown_parameters'),
            'applicability':ref.get('applicability'),'formal_eligible':False})
    packets=[];rows=[];matrices=[];baseline_checks=[]
    for case in cases:
        cid=case['case_id'];text=case['model_response'];segments=core.segment(text)
        require(segments==old_steps[cid]['generated_steps'],'original_segmentation_changed')
        require(core.digest(text)==case['answer_sha256'],'input_answer_changed')
        rep=representation(text,segments,vocab,cid)
        route,declared=core.selected_route(text,refs)
        candidates=[r for r in refs if case['question_id'] in r['question_ids'] and r['route_id']==route]
        require(len(candidates)==1,'original_single_reference_scope_changed');ref=candidates[0];rr=reference_units[ref['reference_id']]
        full_ref=[s['text'] for s in ref['steps']]
        baseline_matrix=encoder.encode(full_ref)@encoder.encode([s['text'] for s in segments]).T
        normalized_matrix=encoder.encode([s['text'] for s in rr['units']])@encoder.encode([s['text'] for s in rep['units']]).T
        gated,excluded,unknown=object_gate(rr['units'],rep['units'],normalized_matrix)
        for threshold in THRESHOLDS:
            original_score=core.score_steps(case,[ref],encoder,threshold)
            original_matrix_score=matrix_score(baseline_matrix,threshold)
            require(original_score['sr']==original_matrix_score['sr'] and original_score['sp']==original_matrix_score['sp'],'baseline_formula_disagreement')
            if threshold==.7:
                require(original_score['sr']==old_steps[cid]['sr'] and original_score['sp']==old_steps[cid]['sp'],'frozen_baseline_not_reproduced')
                baseline_checks.append({'case_id':cid,'original_sr_sp_reproduced':True,'original_segments_reproduced':True})
            for mode,matrix in zip(MODES,[baseline_matrix,normalized_matrix,gated]):
                score=matrix_score(matrix,threshold)
                rows.append({'case_id':cid,'question_id':case['question_id'],'condition':case['condition'],'mode':mode,
                    'threshold':threshold,'reference_id':ref['reference_id'],'full_answer_sha256':case['answer_sha256'],
                    **score,'object_excluded_pairs':len(excluded) if mode.endswith('object_gate') else 0,
                    'formula':'unchanged thresholded row/column maximum coverage','formal_eligible':False})
        matrices.append({'case_id':cid,'reference_id':ref['reference_id'],'baseline_cosine_matrix':baseline_matrix.tolist(),
            'surface_cosine_matrix':normalized_matrix.tolist(),'object_eligible_matrix':(gated>-1).tolist(),
            'object_excluded_pairs':excluded,'object_unknown_pairs_not_gated':unknown,
            'excluded_pairs_above_primary_threshold':sum(x['original_cosine']>=.7 for x in excluded)})
        chosen_match=re.search(r'^\s*(?:\*\*)?Chosen\s+Method:.*$',text,re.I|re.M)
        packets.append({**rep,'case_id':cid,'question_id':case['question_id'],'condition':case['condition'],
            'source_file':bind(OLD/'cases.json'),'json_pointer':f"/cases/{cases.index(case)}/model_response",
            'reference_id':ref['reference_id'],'declared_method_text':declared,
            'declared_method_span':span(text,chosen_match.start(),chosen_match.end()) if chosen_match else None,
            'evidence_for_original_direct_scores':{
                'c_param':'Local parameter spans and duration/temperature absence/presence; reference unknowns retained; no completeness score assigned.',
                'co_order':'Textual operation order and temporal cues; author step order is source evidence, not automatically a required dependency.',
                'co_method':'Declared-method source span and original reference binding; task suitability remains separate and conditional.',
                'co_param':'Parameter span stays with its source unit; multiple-predicate ambiguity is visible, with no value coercion or cross-unit borrowing.',
                'co_chem':'Literal main-object evidence and optional disjoint-object comparison flags, without scientific compatibility adjudication.'},
            'unchanged_E2_direct_judge_scores':{k:e2[cid]['candidate_raw_and_derived'][k] for k in ['c_param','co_order','co_method','co_param','co_chem']},
            'new_direct_scores':None,'semantic_accuracy_validated':False,'formal_eligible':False})
    row_index={(r['case_id'],r['mode'],r['threshold']):r for r in rows};packet_index={r['case_id']:r for r in packets}
    comparisons=[];evidence_changes=[]
    for pair in pairs:
        a,b=(packet_index[pair[s+'_case_id']] for s in ['baseline','variant'])
        ac=Counter(p['kind'] for u in a['units'] for p in u['parameter_evidence']);bc=Counter(p['kind'] for u in b['units'] for p in u['parameter_evidence'])
        atexts=[u['text'] for u in a['units']];btexts=[u['text'] for u in b['units']]
        evidence_changes.append({'pair_id':pair['pair_id'],'question_id':pair['question_id'],'condition':pair['condition'],
            'baseline_units':a['unit_n'],'variant_units':b['unit_n'],'same_ordered_unit_texts':atexts==btexts,
            'same_unit_multiset':Counter(atexts)==Counter(btexts),'baseline_parameters':dict(ac),'variant_parameters':dict(bc),
            'parameter_count_deltas':{k:bc[k]-ac[k] for k in sorted(set(ac)|set(bc))},
            'baseline_direct_scores':a['unchanged_E2_direct_judge_scores'],'variant_direct_scores':b['unchanged_E2_direct_judge_scores'],
            'new_judge_scores_produced':False,'scientific_equivalence_not_assumed_from_unit_equality':True})
        for threshold in THRESHOLDS:
            for mode in MODES:
                av,bv=(row_index[pair[s+'_case_id'],mode,threshold] for s in ['baseline','variant'])
                comparisons.append({'pair_id':pair['pair_id'],'question_id':pair['question_id'],'condition':pair['condition'],
                    'mode':mode,'threshold':threshold,'baseline_case_id':pair['baseline_case_id'],'variant_case_id':pair['variant_case_id'],
                    'same_configuration_and_reference':av['reference_id']==bv['reference_id'],
                    'baseline_sr':av['sr'],'variant_sr':bv['sr'],'delta_sr':bv['sr']-av['sr'],
                    'baseline_sp':av['sp'],'variant_sp':bv['sp'],'delta_sp':bv['sp']-av['sp'],
                    'baseline_n':av['generated_n'],'variant_n':bv['generated_n'],'reference_n':av['reference_n'],
                    'full_text_reparsed_both_arms':True,'formal_eligible':False})
    primary=[r for r in comparisons if r['threshold']==.7]
    by_condition=[]
    for mode in MODES:
        for condition in sorted({r['condition'] for r in pairs}):
            group=[r for r in primary if r['mode']==mode and r['condition']==condition]
            by_condition.append({'mode':mode,'condition':condition,'pairs':len(group),
                **{metric+'_'+direction:sum(test(r['delta_'+metric]) for r in group)
                   for metric in ['sr','sp'] for direction,test in [('negative',lambda x:x < -1e-12),('zero',lambda x:abs(x)<=1e-12),('positive',lambda x:x > 1e-12)]}})
    deletions=deletion_trace({c['case_id']:c for c in cases},refs,pairs,old_steps)
    summary={'status':'completed_offline_candidate','cases':21,'pairs':15,'reference_branches':len(refs),
        'thresholds':THRESHOLDS,'primary_threshold':.7,'modes':MODES,'per_answer_rows':len(rows),'paired_rows':len(comparisons),
        'original_baseline_checks':len(baseline_checks),'primary_condition_results':by_condition,
        'source_span_units':sum(r['unit_n'] for r in packets),'reference_source_span_units':sum(r['unit_n'] for r in reference_packets),
        'parameter_evidence_count':sum(len(u['parameter_evidence']) for r in packets for u in r['units']),
        'multiple_action_mention_units':sum(u['multiple_action_mentions_unresolved'] for r in packets for u in r['units']),
        'object_gate_excluded_pairs':sum(len(r['object_excluded_pairs']) for r in matrices),
        'object_gate_excluded_high_cosine_pairs':sum(r['excluded_pairs_above_primary_threshold'] for r in matrices),
        'deletion_pairs_with_target_already_unmatched_at_baseline':sum(r['all_target_rows_already_unmatched_at_baseline'] for r in deletions),
        'new_variants_created':0,'new_local_embeddings':len(encoder.created),'reused_local_embeddings':len(encoder.reused),
        'new_judge_requests':0,'new_direct_scores':0,'core_or_original_results_changed':False,'formal_eligible':False,'expert_returns':0,
        'claim_boundary':'Source offsets and conditional lexical evidence are software-verifiable. Atomic action semantics, parameter correctness and task suitability remain unconfirmed; this is not a new scoring gold standard.'}
    for name,data in [('evidence_packets.json',packets),('reference_evidence_packets.json',reference_packets),('per_case.json',rows),
        ('paired_results.json',comparisons),('full_matrices.json',matrices),('control_evidence_changes.json',evidence_changes),
        ('deletion_cause_trace.json',deletions),('summary.json',summary)]:save(name,data)
    core.table(OUT/'per_case.csv',rows);core.table(OUT/'paired_results.csv',comparisons);core.table(OUT/'condition_summary.csv',by_condition)
    validate_sources(plan)
    save('verification.json',{'status':'pass','new_judge_requests':0,'network_transports_disabled':True,
        'baseline_checks':baseline_checks,'all_source_character_roundtrips':True,'all_15_pairs_all_three_modes_reparsed':True,
        'existing_inputs_unchanged':True,'encoder_identity':encoder.identity,'cached_vector_hashes':encoder.reused,'new_vector_hashes':encoder.created,
        'plan':bind(OUT/'plan.json'),'script':bind(__file__),'holdout_or_confirmation_accessed':False})
    record('run',status='completed',new_local_embeddings=len(encoder.created),reused_local_embeddings=len(encoder.reused),summary=bind(OUT/'summary.json'))
    write_readme(summary,deletions)
    print(json.dumps({k:summary[k] for k in ['status','cases','pairs','per_answer_rows','paired_rows','source_span_units',
        'object_gate_excluded_high_cosine_pairs','deletion_pairs_with_target_already_unmatched_at_baseline','new_local_embeddings','reused_local_embeddings','new_judge_requests']},ensure_ascii=True))


def write_readme(summary,deletions):
    lines=['# 步骤来源跨度与局部证据候选 v1','',
        '固定原 21 份公开开发全文、15 对受控变体和两份原 FDISCO 参考。原 BioProBench baseline 不变；新增来源偏移、局部参数证据与可选对象一致性门，未调用 judge，未改变五个原直接分项量表。','',
        '候选沿用已验证的英文表面边界归一化，不宣称恢复了原分割器遗漏的正文，也不宣称已实现完整动作语义解析。每个动作词、参数与已识别对象均保留原字符串偏移。参数不移到其他单位；多谓词歧义直接标记。参考文本偏移指向冻结的参考重建字符串，作者原文通过既有 source anchor 单独追溯。','',
        '可选门只拒绝双方都明确识别到唯一且不同对象标识的候选边；未知与混合对象不擅自否定。对象词表由全部冻结参考的字面标识生成，未依据高分答案挑词；浓度、温度与时间不参与此门。完整余弦矩阵与原 SR/SP 均保留。','',
        '| 表示 | 条件 | SR 下降/不变/上升 | SP 下降/不变/上升 |', '|---|---|---:|---:|']
    for r in summary['primary_condition_results']:
        lines.append(f"| {r['mode']} | {r['condition']} | {r['sr_negative']}/{r['sr_zero']}/{r['sr_positive']} | {r['sp_negative']}/{r['sp_zero']}/{r['sp_positive']} |")
    lines += ['',
        '必要步骤删除的 1/3 响应并非直接证明其余变体编辑无效。q21/q22 的目标参考步骤在未删基线已低于 0.7，二值 SR 无法继续降低；逐行最大相似度确实下降。q22 剩余成像前平衡措辞单独展示，不自动视为保留完整 DBE 转移/存储操作。本版未据此篡改原变体或创建补救 ID。','',
        f"原主阈值下，对象门标记了 {summary['object_gate_excluded_high_cosine_pairs']} 个高余弦但明确字面对象冲突的候选边（跨 21 份重复开发文本，不是独立错误数）。这与基线阈值漏匹配是两类问题。",'',
        f"实际新增本地向量 {summary['new_local_embeddings']}，复用 {summary['reused_local_embeddings']}；新 judge 0、新直接评分 0、专家回传 0。",'',
        '[完整来源证据](evidence_packets.json) · [参考来源](reference_evidence_packets.json) · [全部余弦矩阵和对象门](full_matrices.json) · [删步原因](deletion_cause_trace.json) · [15 对各阈值结果](paired_results.csv) · [控制证据变化](control_evidence_changes.json) · [核验](verification.json)','',
        '```powershell',f"& '{sys.executable}' scripts/cce_step_representation_optimizer_v1.py prepare",f"& '{sys.executable}' scripts/cce_step_representation_optimizer_v1.py run",'```','',
        '本结果是开发候选与可核验字面证据；未用留出、独立确认集或模型成功结果调规则。不得把来源偏移正确、合并不变或对象门数字改善当作科学准确率。']
    (OUT/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['prepare','run'])
    args=parser.parse_args()
    {'prepare':prepare,'run':run}[args.command]()
