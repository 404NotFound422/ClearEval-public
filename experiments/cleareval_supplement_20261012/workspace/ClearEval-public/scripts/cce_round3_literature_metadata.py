"""Save public Crossref metadata and exact query endpoints for the problem cycle."""
import hashlib,json,sys,urllib.request,urllib.parse
from datetime import datetime,timezone
from pathlib import Path
OUT=Path(__file__).resolve().parents[1]/'artifacts/cce_validation/optimizer_round3_20261011/problem_cycles/literature_metadata_01'
DOIS=['10.18653/v1/2020.acl-main.442','10.18653/v1/2021.emnlp-main.575',
      '10.18653/v1/2025.coling-main.21','10.18653/v1/2026.acl-long.764']

def main():
    OUT.mkdir(parents=True,exist_ok=False)
    records=[]
    for doi in DOIS:
        url='https://api.crossref.org/works/'+urllib.parse.quote(doi,safe='')
        record={'database':'Crossref','endpoint':url,'doi':doi,'queried_utc':datetime.now(timezone.utc).isoformat()}
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'ClearEval-ResearchMetadata/1.0'})
            with urllib.request.urlopen(req,timeout=25) as response:
                body=response.read();record['http_status']=response.status
            name=doi.replace('/','_')+'.json';(OUT/name).write_bytes(body)
            data=json.loads(body)['message']
            record.update(status='ok',raw_json=name,sha256=hashlib.sha256(body).hexdigest(),
                title=data.get('title'),type=data.get('type'),published=data.get('published'),
                venue=data.get('container-title'),returned_doi=data.get('DOI'))
        except Exception as exc:
            record.update(status='failed',error_type=type(exc).__name__,error=str(exc))
        records.append(record);print(json.dumps(record,ensure_ascii=True),flush=True)
    (OUT/'queries.json').write_text(json.dumps({'actual_command':[sys.executable,*sys.argv],
        'databases_queried':['Crossref'],'queries':records,'new_model_calls':0},ensure_ascii=False,indent=2)+'\n',encoding='utf8')

if __name__=='__main__':main()
