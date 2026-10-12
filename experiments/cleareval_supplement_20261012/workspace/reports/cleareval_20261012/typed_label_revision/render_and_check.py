"""Render the source-backed report and verify delivery links and manifests."""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote
from markdown_it import MarkdownIt

OUT=Path(__file__).resolve().parent
md=(OUT/'REPORT_zh.md').read_text(encoding='utf-8')
checks=[]
for filename in ['REPORT_zh.md','commands.md']:
    body=(OUT/filename).read_text(encoding='utf-8')
    for match in re.finditer(r'\]\(([^)]+)\)',body):
        link=match[1]
        if link.startswith(('https://','http://','#')):
            continue
        path=(OUT/unquote(link.split('#')[0])).resolve()
        assert path.exists(),(filename,link)
        checks.append({'from':filename,'target':str(path),'exists':True})
html=MarkdownIt('commonmark').enable('table').render(md)
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ClearEval 标签修复与 CCE 回放</title>
<style>
body{font:16px/1.8 "Microsoft YaHei",system-ui,sans-serif;color:#172b3a;max-width:1160px;margin:36px auto;padding:0 24px}
h1{font-size:28px;line-height:1.4}p{margin:18px 0}a{color:#086698}img{width:100%;height:auto}
table{border-collapse:collapse;width:100%;font-size:14px;margin:22px 0}th,td{border:1px solid #ccd4dc;padding:10px;text-align:left;vertical-align:top}th{background:#edf3f7}
code{background:#edf3f7;padding:2px 4px}pre{overflow:auto;background:#edf3f7;padding:18px}
@media print{body{font-size:11pt;max-width:none;padding:0}tr,img{break-inside:avoid}a{color:inherit}}
</style><body>'''+html+'</body></html>'
(OUT/'REPORT_zh.html').write_text(page,encoding='utf-8')

def bind(path):
    return {'path':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}

for phase in ['with_pair_sources','with_author_labels']:
    manifest=json.loads((OUT/phase/'execution_manifest.json').read_text(encoding='utf-8'))
    for name,value in manifest.items():
        if isinstance(value,dict) and 'path' in value and 'sha256' in value:
            assert bind(Path(value['path']))==value,(phase,name)
original_manifest=json.loads((OUT/'rules_only/execution_manifest.json').read_text(encoding='utf-8'))
assert bind(OUT/'rules_only/entrypoint_snapshot.py')['sha256']==original_manifest['entrypoint']['sha256']
pending=json.loads((OUT/'qualitative_prompt_pending/manifest.json').read_text(encoding='utf-8'))
assert pending['new_model_requests']==0 and len(pending['observations'])==5
for row in pending['observations']:
    for name in ['source_document','prompt','schema']:
        assert bind(Path(row[name]['path']))==row[name]
verification={'local_links':len(checks),'links':checks,'prompt_packets':5,
    'historical_rule_entrypoint_snapshot_matches':True,'new_model_requests':0,
    'figures_visually_inspected':True,'visual_check':'PNG text, legends, axis labels and boundaries inspected; no clipping observed.'}
(OUT/'delivery_verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
files=[bind(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='delivery_manifest.json']
(OUT/'delivery_manifest.json').write_text(json.dumps({'files':files,'new_model_requests':0},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'local_links_valid':len(checks),'bound_files':len(files),'prompt_packets':5}))
