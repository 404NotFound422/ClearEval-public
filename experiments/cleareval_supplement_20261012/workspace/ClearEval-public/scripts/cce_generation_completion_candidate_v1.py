"""Generation-only candidate: preserve v11 schema order and request concise records.

No model-call CLI. The original parser, source gates, formulae and wire version
remain unchanged. A caller must preserve property order through storage and HTTP.
"""
from __future__ import annotations
import argparse, copy, hashlib, json, sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import cce_grounded_extraction_v11 as original
import cce_round2_runner_v11 as runner
OUT=ROOT/'artifacts/cce_validation/optimizer_round2_20261010/generation_completion_candidate_v1'
CANDIDATE_VERSION='generation_completion_v1'
VERSION=original.VERSION
GENERATION_NOTE='''[GENERATION COMPLETION POLICY v1]
Output one compact JSON object on one line, without indentation, Markdown or text outside JSON. Emit its top-level keys in this order: scores, score_evidence, grounded_extraction. Finish the five original score records and their five evidence records before the extraction arrays. This changes serialization order only; preserve the original scoring rubric and every required extraction field.
Each entity record must correspond to a distinct source-backed identity/occurrence/use. Do not allocate another entity ID to repeat the same complete literal, source Unit, complete-name occurrence, kind and usage. Reuse an existing entity ID when several relations or intrinsic records refer to that same entity. Preserve genuinely different complete names, qualifiers, source occurrences, alternatives, roles and uses; do not merge them just to shorten the response. Do not repeatedly append surrounding experimental conditions to a name or re-enumerate already emitted records. Keep every source-supported operation and all explicit uncertainty; no fixed entity-count cap, truncation, empty-array shortcut or omitted difficult fact is permitted. Concise wording is allowed for reasoning, but keep the concrete basis and uncertainty needed by the original rubric.
'''

def __getattr__(name):return getattr(original,name)
def digest_bytes(value):return hashlib.sha256(value).hexdigest()
def ordered_json(value):
    """JSON wire bytes preserve insertion order; canonical hashes remain separate."""
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8')
def schema():return copy.deepcopy(original.schema())
def schema_for_document(doc):return copy.deepcopy(original.schema_for_document(doc))
def make_prompt(case,doc):return original.make_prompt(case,doc)+'\n'+GENERATION_NOTE
def convert(raw,doc):return original.convert(raw,doc)
def payload_for(prompt,spec,public):
    # Do not rebuild a sorted disk schema. Always call schema_for_document(doc)
    # at preparation time, then preserve its order through ordered_json storage.
    require_top_order(spec)
    return runner.payload_for(prompt,spec,public)
def require_top_order(spec):
    if list(spec['properties'])!=['scores','score_evidence','grounded_extraction']:
        raise ValueError('SCHEMA_PROPERTY_ORDER_CHANGED')
def write_ordered_once(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f:f.write(ordered_json(value)+b'\n')
def format_order_manifest(payload):
    spec=payload['format'];require_top_order(spec)
    return {'top_properties':list(spec['properties']),
            'grounded_properties':list(spec['properties']['grounded_extraction']['properties']),
            'ordered_format_sha256':digest_bytes(ordered_json(spec)),
            'ordered_payload_sha256':digest_bytes(ordered_json(payload)),
            'semantic_payload_sha256':runner.j.digest(payload)}

def offline_checks(out):
    rows=[]
    def check(name,value):
        rows.append({'check':name,'passed':bool(value)})
        if not value:raise AssertionError(name)
    doc,wire=original.synthetic_fixture()
    spec=schema_for_document(doc);oldspec=original.schema_for_document(doc)
    check('schema_semantics_unchanged',spec==oldspec)
    check('all_schema_properties_unchanged',runner.j.digest(spec)==runner.j.digest(oldspec))
    check('original_score_first_order',list(spec['properties'])==['scores','score_evidence','grounded_extraction'])
    entities=spec['properties']['grounded_extraction']['properties']['entities']
    check('no_array_or_entity_cap_added',entities==oldspec['properties']['grounded_extraction']['properties']['entities'] and 'maxItems' not in entities)
    decoded=json.loads(ordered_json(spec));check('order_survives_own_storage',list(decoded['properties'])==list(spec['properties']))
    sorted_schema=json.loads(runner.j.canonical(spec));check('reproduced_old_sorted_storage_failure',list(sorted_schema['properties'])==['grounded_extraction','score_evidence','scores'])
    try:require_top_order(sorted_schema);rejected=False
    except ValueError:rejected=True
    check('sorted_schema_detected_before_request',rejected)
    raw=original.canonical(wire)
    check('same_raw_conversion_exact',convert(raw,doc)==original.convert(raw,doc))
    check('wire_version_unchanged',VERSION==original.VERSION)
    pretty=json.dumps(wire,ensure_ascii=False,indent=2);compact=ordered_json(wire).decode('utf8')
    check('compact_has_same_JSON_values',json.loads(pretty)==json.loads(compact))
    check('compact_raw_not_repaired_after_generation',len(compact.encode())<len(pretty.encode()))
    check('duplicate_JSON_still_rejected',_reject_duplicate(doc))
    public={'model':'SYNTHETIC_LOCAL_ONLY','num_ctx':98304,'max_output_tokens':8192,'temperature':0,'enable_thinking':False}
    payload=payload_for('Synthetic software-only prompt.',spec,public)
    # Exact production HTTP serialization, with the opener replaced at its only
    # I/O boundary. No localhost/network service or real case is consulted.
    from models.Ollama_LLM import LocalOllamaHTTPClient
    client=LocalOllamaHTTPClient();captured={}
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return b'{"response":"{}","done":true,"done_reason":"stop"}'
    class Opener:
        def open(self,request,timeout):captured['bytes']=request.data;return Response()
    client.opener=Opener();client.generate(**payload);client.close()
    sent=json.loads(captured['bytes']);check('actual_HTTP_serializer_retains_score_first',list(sent['format']['properties'])==list(spec['properties']))
    check('actual_HTTP_serializer_keeps_all_schema_values',sent==payload)
    check('model_options_unchanged',sent['options']=={'num_ctx':98304,'num_predict':8192,'temperature':0})
    result={'status':'pass','candidate_version':CANDIDATE_VERSION,'wire_version':VERSION,'checks':rows,
      'script_sha256':digest_bytes(Path(__file__).read_bytes()),'original_module_sha256':digest_bytes(Path(original.__file__).read_bytes()),
      'original_runner_sha256':digest_bytes(Path(runner.__file__).read_bytes()),
      'synthetic_only':True,'source_answer_bodies_read':0,'new_model_calls':0,'HTTP_boundary_stubbed':True,
      'scope':'Software order preservation and unchanged conversion only; generation completion and factual recall not tested.',
      'synthetic_compact_bytes':len(compact.encode()),'synthetic_pretty_bytes':len(pretty.encode()),
      'http_payload_order':format_order_manifest(sent)}
    out.mkdir(parents=True,exist_ok=True)
    write_ordered_once(out/'software_checks.json',result)
    write_ordered_once(out/'schema.json',spec)
    (out/'generation_note.txt').write_text(GENERATION_NOTE,encoding='utf8')
    print(json.dumps({'status':'pass','checks':len(rows),'out':str(out),'new_model_calls':0}))
def _reject_duplicate(doc):
    try:convert('{"scores":{},"scores":{}}',doc)
    except Exception:return True
    return False
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['self-check']);p.add_argument('--out',type=Path,default=OUT/'software_execution_01')
    a=p.parse_args();offline_checks(a.out)
if __name__=='__main__':main()
