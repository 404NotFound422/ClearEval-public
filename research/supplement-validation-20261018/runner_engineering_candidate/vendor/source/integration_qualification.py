"""Qualification wiring; never mutates demand vectors or score arithmetic."""
import hashlib,json
from pathlib import Path
from copy import deepcopy
from requirement_facts import qualify
from evaluation_contract import json_hash
BINDING=Path(__file__).with_name('integration_archived_demands.json')

def demand_status(question, preferences):
    proposal={'vector':deepcopy(preferences)}
    binding='NO_MATCHING_REVIEWED_PROPOSAL; VECTOR_ONLY_UNVERIFIED'
    archived=json.loads(BINDING.read_text())['proposals']
    found=archived.get(str(question['question_id']))
    # Historical proposal binds canonical whole-question JSON, not text bytes.
    sha=json_hash(question)
    if found and found.get('question_sha256')==sha and found.get('vector')==preferences:
        proposal=deepcopy(found);binding='EXACT_ARCHIVED_QUESTION_AND_VECTOR'
    result=qualify(question,proposal)
    result['proposal_binding']=binding
    result['proposal_hash_format']='CANONICAL_WHOLE_QUESTION_JSON_SHA256'
    result['fact_hash_format']='UTF8_QUESTION_TEXT_SHA256'
    return result
