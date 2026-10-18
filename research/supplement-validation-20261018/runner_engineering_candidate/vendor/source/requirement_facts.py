"""Non-numeric, fail-closed development annotation layer. Not scientific gold."""
import copy
import hashlib
import json
import math
from pathlib import Path
import re

VERSION = 'requirement-facts-candidate-v1'
AXES = ('fluorescence_protein_preservation','dye_permeability','clearing_challenge','geometry_preference','operational_economy','safety_compatibility')
ANNOTATIONS = Path(__file__).with_name('archived_annotations.json')

def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def source_segments(text):
    # Include separators/whitespace, too: concatenation must reproduce every byte.
    return [{'start':m.start(),'end':m.end(),'quote':m.group()} for m in re.finditer(r'[^。；;\n]+[。；;]?|[。；;\n]', text)]

def validate_spans(text, segments, partition=False):
    for s in segments:
        a,b=s['start'],s['end']
        if type(a) is not int or type(b) is not int or not (0 <= a < b <= len(text)) or s['quote'] != text[a:b]:
            raise ValueError('Invalid source span')
    if partition and (''.join(s['quote'] for s in segments) != text or any(s['start'] != (segments[i-1]['end'] if i else 0) for i,s in enumerate(segments))):
        raise ValueError('Source partition is not lossless')

def capture(question, annotation=None):
    text = question.get('question')
    if not isinstance(text, str) or not text.strip():
        return {'schema_version':VERSION,'source_retention_status':'UNKNOWN','requirements_semantic_coverage':'UNKNOWN','unrepresented_requirements_retained':None,'failure':'MISSING_OR_EMPTY_SOURCE','facts':[]}
    segments=source_segments(text)
    validate_spans(text,segments,True)
    result={'schema_version':VERSION,'question_id':question.get('question_id'),'question_sha256':sha(text),'source_text':text,'source_segments':segments,'source_retention_status':'LOSSLESS_EXACT_PARTITION','requirements_semantic_coverage':'UNKNOWN','unrepresented_requirements_retained':None,'annotation_origin':'NONE','facts':[], 'priority_status':'UNKNOWN_NOT_INFERRED_FROM_ZERO_WEIGHTS','numeric_projection_authorized':False,'scientific_certified':False}
    if annotation is None:
        try:
            annotation=json.loads(ANNOTATIONS.read_text(encoding='utf-8')).get(str(question.get('question_id')))
        except (OSError,ValueError):
            result['failure']='ANNOTATION_UNAVAILABLE'
            return result
    if annotation is None:
        result['failure']='NO_REVIEW_CANDIDATE_FOR_SOURCE'
        return result
    try:
        if annotation['question_sha256'] != sha(text):
            raise ValueError('Annotation source SHA mismatch')
        validate_spans(text,annotation['facts'])
        # Every non-whitespace source clause has an explicit reviewed role.
        reviewed=annotation['clause_reviews']
        validate_spans(text,reviewed)
        if [(x['start'],x['end'],x['quote']) for x in reviewed] != [(x['start'],x['end'],x['quote']) for x in segments if x['quote'].strip()]:
            raise ValueError('Incomplete clause review')
        for f in annotation['facts'] + reviewed:
            if not f.get('roles') or not f.get('reason') or f.get('numeric_projection_authorized') is not False:
                raise ValueError('Incomplete role/reason or unsafe numeric authorization')
            for m in f.get('axis_candidates',[]):
                if m.get('axis') not in AXES or m.get('status') not in ('SEMANTIC_CANDIDATE_ONLY','RELATED_BUT_INSUFFICIENT','EXPLICIT_NON_PRIORITY') or not m.get('reason'):
                    raise ValueError('Invalid axis candidate')
        result['unrepresented_requirement_clauses']=[copy.deepcopy(f) for f in reviewed if any(r in ('REQUIRED_GOAL','REQUIRED_TARGET_CONSTRAINT','CONDITIONAL_GOAL','CONDITIONAL_OPTION','OPTIMIZATION_PREFERENCE','CONDITIONAL_OPTIMIZATION_PREFERENCE','CONDITIONAL_LIMITATION') for r in f['roles'])]
        result.update({'annotation_origin':'DEVELOPMENT_ASSISTANT_REVIEW_CANDIDATE_NOT_INDEPENDENT_EXPERIMENT_OR_EXPERT_GOLD','requirements_semantic_coverage':'DEVELOPMENT_CLAUSE_REVIEW_PENDING_INDEPENDENT_REVIEW','priority_status':annotation['priority_status'],'facts':copy.deepcopy(annotation['facts']),'clause_reviews':copy.deepcopy(reviewed),'unrepresented_facts':[copy.deepcopy(f) for f in annotation['facts'] if not f.get('axis_candidates') or any(m['status'] != 'SEMANTIC_CANDIDATE_ONLY' for m in f.get('axis_candidates',[]))]})
        # Source retention is verified; semantic exhaustiveness is deliberately not certified.
    except (KeyError,TypeError,ValueError) as e:
        result['failure']='INVALID_ANNOTATION: '+str(e)
    return result

def qualify(question, proposal):
    facts=capture(question)
    vector=proposal.get('vector') if isinstance(proposal,dict) else None
    valid=isinstance(vector,dict) and set(vector)==set(AXES) and all(isinstance(vector[a],dict) and type(vector[a].get('weight')) in (int,float) and 0 <= vector[a]['weight'] <= 1 and type(vector[a].get('target')) in (int,float) and math.isfinite(vector[a]['target']) for a in AXES)
    all_zero=all(vector[a]['weight']==0 for a in AXES) if valid else None
    return {'question_sha256':facts.get('question_sha256'),'source_text':facts.get('source_text'),'source_clauses':facts.get('source_segments',[]),'source_retention_status':facts['source_retention_status'],'requirements_semantic_coverage':facts['requirements_semantic_coverage'],'unrepresented_requirements_retained':None,'unmapped_requirements_absent':None,'all_projected_weights_zero':all_zero,'projection_status':'UNKNOWN' if not valid or facts.get('failure') else ('ALL_ZERO_INCOMPLETE' if all_zero else 'PARTIAL_UNCALIBRATED'),'s_method_use':'DIAGNOSTIC_ONLY','aggregate_IA_use':'DIAGNOSTIC_ONLY_NOT_END_TO_END_VALIDATED','numeric_vector_unchanged':True,'scientific_certified':False,'fact_capture':facts,'original_matched_requirements':copy.deepcopy(proposal.get('requirements',[])) if isinstance(proposal,dict) else [],'original_axis_audits':copy.deepcopy(proposal.get('axis_audits',{})) if isinstance(proposal,dict) else {}}
