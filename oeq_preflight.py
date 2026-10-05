"""Read-only OEQ input/KB/config preflight, with no model clients or secrets printed."""
from pathlib import Path
from collections import Counter
import argparse
import json
import math
import sys

# Embedded Python with a ._pth file does not add the script directory.
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluation_contract import FixedDemandRegistry, CurrentDemandRegistry, json_hash, sha256_file
from experiments.construct_validity.contract import read


def run_preflight(workspace='.', question_file='dataset/Q+AR/src/question_final.json',
                  demand_file='dataset/Q+AR/src/demand_vectors_all.json', demand_manifest=None,
                  model_config='config/config.yaml', require_model=True, demand_profile='fixed'):
    root = Path(workspace).resolve()
    def path(name):
        p=Path(name)
        return p if p.is_absolute() else root/p
    issues, hashes, coverage = [], {}, {}
    def issue(code,severity,detail,**extra):
        issues.append({'code':code,'severity':severity,'detail':detail,**extra})
    def load(name):
        p=path(name)
        if not p.is_file():
            issue('MISSING_INPUT','ERROR',name)
            return None
        hashes[name]=sha256_file(p)
        try: return read(p)
        except Exception as exc:
            issue('INVALID_JSON','ERROR',name,error_type=type(exc).__name__)
            return None
    q=load(str(question_file))
    if demand_profile == 'current-proposal':
        if q is not None:
            try:
                registry=CurrentDemandRegistry(path(question_file))
                coverage['questions']=len(registry.questions)
                coverage['fixed_demand_binding']='CURRENT_TASK_PROJECTION_MATCHED'
                coverage['demand_profile']=demand_profile
                coverage['demand_projection']=registry.provenance
                issue('CURRENT_DEMAND_NOT_EXPERT_CALIBRATED','WARNING',
                      'Current task projection is reproducible; numeric scales and scientific approval remain pending')
            except (ValueError,OSError,KeyError,TypeError) as exc:
                issue('CURRENT_DEMAND_DERIVATION_FAILED','ERROR',str(exc))
    elif demand_profile == 'fixed':
        dv=load(str(demand_file))
        manifest_name=str(demand_manifest or str(demand_file)+'.manifest.json')
        dm=load(manifest_name)
        if q is not None and dv is not None and dm is not None:
            try:
                registry=FixedDemandRegistry(path(question_file),path(demand_file),path(manifest_name))
                coverage['questions']=len(registry.questions)
                coverage['fixed_demand_binding']='MATCHED'
                coverage['demand_profile']=demand_profile
            except (ValueError,OSError) as exc:
                coverage['fixed_demand_binding']='MISMATCH'
                issue('QUESTION_DEMAND_VERSION_MISMATCH','ERROR',str(exc),compatible_snapshot=dm.get('questions_file'))
    else:
        issue('INVALID_DEMAND_PROFILE','ERROR','Unknown demand profile')
    required=['KnowledgeBase/tissue.json','KnowledgeBase/method_fluro_compati.json','KnowledgeBase/time_kb.json',
              'KnowledgeBase/tissue_ri.json','KnowledgeBase/method_ri_ref.json','KnowledgeBase/method_sigma_ri.json',
              'dataset/Q+AR/src/model_space_signed.json','dataset/Q+AR/src/model_space.json']
    values={name:load(name) for name in required}
    time=values['KnowledgeBase/time_kb.json'] or {}
    rows=time.get('rows',[])
    coverage['time_rows']=len(rows)
    keys=[r.get('lookup_key') for r in rows]
    if len(keys)!=len(set(keys)):
        issue('DUPLICATE_TIME_ROWS','ERROR','Duplicate method/tier time reference')
    bad, scope_conflicts = [], []
    for row in rows:
        bounds=[row.get(k) for k in ('clearing_time_min_h','clearing_time_median_h','clearing_time_max_h')]
        if not all(type(x) in {int,float} and math.isfinite(x) for x in bounds) or not 0 <= bounds[0] <= bounds[1] <= bounds[2] or bounds[1] <= 0:
            bad.append(row.get('lookup_key'))
        excludes=row.get('time_excludes_labeling') in {True,'yes'}
        scope=row.get('time_scope','')
        if excludes and ('包括' in scope and '不包括' not in scope and ('染色步骤' in scope or '标记步骤' in scope)):
            scope_conflicts.append(row.get('lookup_key'))
        if not row.get('source_url') or not row.get('time_scope'):
            issue('TIME_SOURCE_OR_SCOPE_MISSING','WARNING','Time row lacks source URL or scope',row_id=row.get('lookup_key'))
    if bad: issue('INVALID_TIME_BOUNDS','ERROR','Time ranges invalid',rows=bad)
    if scope_conflicts: issue('TIME_SCOPE_CONFLICT','WARNING','Excludes-labeling flag conflicts with written scope; time diagnostic requires review',rows=scope_conflicts)
    coverage['time_scope_conflicts']=len(scope_conflicts)
    compatibility=values['KnowledgeBase/method_fluro_compati.json'] or []
    method_names=[r.get('method') for r in compatibility]
    if len(method_names)!=len(set(method_names)): issue('DUPLICATE_METHOD_IDENTITIES','ERROR','Compatibility rows repeat method identity')
    refs=(values['KnowledgeBase/method_ri_ref.json'] or {}).get('ri_ref',{})
    coverage['ri_methods']=len(refs)
    coverage['compatibility_methods']=len(compatibility)
    missing=sorted(set(refs)-set(method_names))
    if missing: issue('COMPATIBILITY_COVERAGE_GAP','WARNING','Missing is unknown, never full credit or established incompatibility',methods=missing)
    no_provenance=sum(isinstance(v,(float,int)) and not isinstance(v,bool) for r in compatibility for k,v in r.items() if k!='method')
    coverage['compatibility_cells_without_individual_source_bindings']=no_provenance
    issue('HEURISTIC_KB_NOT_CALIBRATED','WARNING','Compatibility, capability and RI heuristics lack independent cell-level calibration; retain as diagnostics',cells=no_provenance)
    chunks=list((root/'KnowledgeBase/article_chunk').glob('*.json'))
    coverage['article_chunk_files']=len(chunks)
    replacement=[]
    for p in chunks:
        try:
            value=read(p)
            if '\ufffd' in json.dumps(value,ensure_ascii=False): replacement.append(p.name)
        except Exception: issue('INVALID_ARTICLE_CHUNK','ERROR',p.name)
    if replacement: issue('ARTICLE_TEXT_REPLACEMENT_CHARACTERS','WARNING','Stored article summaries contain replacement characters',files=replacement)
    # Source identity/version registry is useful metadata; it does not bind full-text passages.
    catalog=root/'KnowledgeBase/source_registry.json'
    if catalog.exists():
        value=load('KnowledgeBase/source_registry.json') or {}
        coverage['source_registry_entries']=len(value.get('sources',[]))
        coverage['primary_snapshots_bound']=sum(s.get('snapshot') is not None for s in value.get('sources',[]))
        verified=0
        for source in value.get('sources',[]):
            snapshot=source.get('snapshot')
            if not snapshot: continue
            try:
                if snapshot.get('identity_url') != source['identity']['url'] or snapshot.get('version') != source['identity']['version']:
                    raise ValueError('Source identity/version differs from snapshot')
                for prefix in ('raw','text'):
                    file=path(snapshot[prefix+'_path']).resolve()
                    if not file.is_relative_to(root): raise ValueError('Snapshot path escapes workspace')
                    if sha256_file(file) != snapshot[prefix+'_sha256']: raise ValueError('Primary snapshot content differs')
                body=path(snapshot['text_path']).read_text(encoding='utf-8')
                for passage in source.get('passages',[]):
                    start,end=passage['start'],passage['end']
                    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(body) or body[start:end] != passage['quote']:
                        raise ValueError('Primary passage location differs')
                    import hashlib
                    if hashlib.sha256(passage['quote'].encode('utf-8')).hexdigest() != passage['sha256']:
                        raise ValueError('Primary passage hash differs')
                verified+=1
            except (KeyError,ValueError,OSError,TypeError) as exc:
                issue('PRIMARY_SNAPSHOT_INTEGRITY_FAILURE','ERROR','Primary source binding could not be verified',source_id=source.get('id'),error_type=type(exc).__name__)
        coverage['primary_snapshots_integrity_verified']=verified
    else: issue('PRIMARY_SOURCE_REGISTRY_MISSING','WARNING','Primary source identity/version registry is absent')
    issue('PRIMARY_PASSAGES_PENDING','WARNING','Bibliographic records and summaries alone cannot certify entailment/applicability')
    if require_model:
        for name in ('dataset/Q+AR/src/restrict.py','dataset/Q+AR/src/standard_response.json','prompts/eval_teacher_protocol_review.py'):
            if not path(name).is_file(): issue('MISSING_RUNTIME_RESOURCE','ERROR',name)
        p=path(model_config)
        if not p.is_file(): issue('MISSING_MODEL_CONFIG','ERROR',str(model_config))
        else:
            hashes['model_config']=sha256_file(p)
            try:
                from models.Model_Loader import read_model_config
                config=read_model_config(p)
                models=config.get('models',[])
                names=[str(m.get('name','')).strip() for m in models]
                if not names or any(not n for n in names) or len(names)!=len(set(names)):
                    issue('INVALID_MODEL_IDENTITIES','ERROR','Empty or duplicate normalized model names')
                coverage['configured_model_names']=names
                coverage['configured_model_types']=dict(Counter(m.get('type','UNDECLARED') for m in models))
                # Never include tokens, base URLs or the parsed config in the report.
            except Exception as exc: issue('MODEL_CONFIG_UNREADABLE','ERROR','Cannot parse configuration',error_type=type(exc).__name__)
    return {'technical_ready':not any(i['severity']=='ERROR' for i in issues),'scientific_ready':None,
            'issues':issues,'input_sha256':hashes,'coverage':coverage,'network_requests':0,
            'interpretation':'Read-only engineering preflight; expert scientific validation remains pending'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workspace',default='.')
    p.add_argument('--question-file',default='dataset/Q+AR/src/question_final.json')
    p.add_argument('--demand-vectors',default='dataset/Q+AR/src/demand_vectors_all.json')
    p.add_argument('--demand-manifest')
    p.add_argument('--model-config',default='config/config.yaml')
    p.add_argument('--kb-only',action='store_true')
    p.add_argument('--out')
    args=p.parse_args()
    result=run_preflight(args.workspace,args.question_file,args.demand_vectors,args.demand_manifest,args.model_config,not args.kb_only)
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if args.out:
        out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(text+'\n',encoding='utf-8')
    print(text)
    return 0 if result['technical_ready'] else 2

if __name__=='__main__':
    import sys
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())