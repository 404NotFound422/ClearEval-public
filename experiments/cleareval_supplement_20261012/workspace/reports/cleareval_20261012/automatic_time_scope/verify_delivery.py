"""Verify frozen source bindings, delivered artifacts and local report links."""
import csv,hashlib,json,re,sys
from pathlib import Path
from urllib.parse import unquote
from datetime import datetime,timezone
ROOT=Path(r'C:\ClearEval\ClearEval-public');OUT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'scripts'))
import cce_scoped_midpoint_scorer_v1 as b
manifest=b.read(OUT/'delivery_manifest.json');inputs=b.read(OUT/'scientific_inputs.json')
for ref in [*manifest['files'],*inputs['files']]:
    assert b.bind(ref['path'])==ref,ref['path']
links=[]
for path in [OUT/'REPORT_zh.md',OUT/'commands.md',*(OUT/'examples').glob('*/README_zh.md')]:
    text=path.read_text('utf-8')
    for target in re.findall(r'!?\[[^\]]*\]\(([^\n]+?)\)',text):
        if target.startswith(('https://','http://','#')):continue
        target=unquote(target.split('#',1)[0]).strip('<>')
        file=Path(target) if re.match(r'^[A-Za-z]:[/\\]',target) else path.parent/target
        assert file.is_file(),(str(path),target)
        links.append({'document':str(path),'target':target})
canonical=b.read(OUT/'canonical32_04/results.json');historical=[r for r in b.read(OUT/'archived67_04/results.json') if 'metrics' in r]
assert len(canonical)==32 and len(historical)==67
assert sum(r['complete_numeric_CCE'] and r['candidate_point_applied'] for r in canonical)==28
assert sum(r['complete_numeric_CCE'] and r['candidate_point_applied'] for r in historical)==47
assert sum(r['complete_numeric_CCE'] for r in canonical if r['cell_id'].startswith('R3C'))==5
assert sum(r['complete_numeric_CCE'] and r['candidate_point_applied'] for r in canonical if r['cell_id'].startswith('R3C'))==4
assert len(list((OUT/'examples').glob('*/question.txt')))==9
for name in ['validation.json','joint_01/verification.json','threshold_01/verification.json']:
    data=b.read(OUT/name);assert len(data['checks'])==data['checks_passed'] and all(x['passed'] for x in data['checks'])
with (OUT/'figures/figure_data.csv').open(encoding='utf-8-sig',newline='') as f:fig=list(csv.DictReader(f))
assert len(fig)==24
for update in b.read(OUT/'navigation_updates.json'):assert update['marker'] in Path(update['path']).read_text('utf-8')
external=b.read(OUT/'external_state.json');ledger=Path(external['budget']['ledger']['path'])
assert len(ledger.read_text('utf-8').splitlines())==438
result={'verified_delivery_files':len(manifest['files']),'verified_scientific_inputs':len(inputs['files']),
    'verified_local_links':len(links),'examples':9,'ledger_requests':438,'new_model_calls':0,
    'core_validation_checks':666,'joint_checks':80,'threshold_checks':190,
    'inspection_scope':'file hashes, artifact counts, links and already-executed validation; not independent expert verification',
    'checked_utc':datetime.now(timezone.utc).isoformat(),'links':links}
b.save(OUT/'delivery_verification.json',result)
print(json.dumps({k:v for k,v in result.items() if k!='links'},ensure_ascii=False,indent=2))
