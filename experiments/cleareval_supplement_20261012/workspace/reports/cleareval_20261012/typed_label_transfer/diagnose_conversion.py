"""Inspect archived partial returns with the previously repaired local auditor."""
import json
import sys
from pathlib import Path
ROOT=Path(r'C:\ClearEval\ClearEval-public')
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts'))
import cce_scoped_midpoint_scorer_v1 as b
import cce_posthoc_source_backend_v3 as ground
from cce_record_diagnostics_v2 import records_audit
from cce_posthoc_components_v7 import original

results=[]
for row in b.read(OUT/'scope_candidate_02/results.json'):
    if row['original_status']!='partial':continue
    raw_path=Path(row['source_record']['path']).parent/'raw_response.txt'
    raw=raw_path.read_text(encoding='utf-8')
    payload=original.base.integrity.parse_judge_object(raw)
    doc=b.read(row['source_document']['path'])
    records,errors,duplicates=records_audit(payload,doc,ground)
    failures=[]
    for record in records:
        if record['valid_shape_and_local_source']:continue
        item={'pointer':record['pointer'],'raw_record':record['raw_record'],'errors':record['errors']}
        if record['group'] in ['method_mentions','entities'] and 'u' in record['resolved_fields']:
            item['inventory']=ground.name_occurrence_inventory(record['raw_record']['n'],record['resolved_fields']['u'],doc)
            item['support']=record['resolved_fields']['u']
        failures.append(item)
    results.append({'cell_id':row['cell_id'],'raw':b.bind(raw_path),'source_document':row['source_document'],
        'records':len(records),'valid_local_records':sum(r['valid_shape_and_local_source'] for r in records),
        'failures':failures,'duplicate_ids':duplicates,'source_role_interpretation_not_validated':True,
        'new_model_calls':0,'score_changed':False})
b.save(OUT/'conversion_diagnosis.json',{'entrypoint':b.bind(__file__),'auditor':b.bind(sys.modules[records_audit.__module__].__file__),
       'results':results,'execution':[sys.executable,*sys.argv]})
for result in results:
    print(json.dumps({'cell_id':result['cell_id'],'records':result['records'],'valid':result['valid_local_records'],
        'failures':[{'record':x['raw_record'],'exact_count':x.get('inventory',{}).get('exact_occurrence_count'),
            'rejections':x.get('inventory',{}).get('rejected_substring_occurrences'),
            'source':x.get('support',{}).get('quote')} for x in result['failures']]},ensure_ascii=False))
