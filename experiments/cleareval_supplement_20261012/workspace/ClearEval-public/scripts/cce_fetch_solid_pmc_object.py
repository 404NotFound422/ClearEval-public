"""Retrieve the exact SOLID supplementary PDF from the locally indexed PMC OA object."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
INDEX = Path(r'C:\ClearEval\literature\tissue_optical_clearing\sources\pmc_s3\PMC11436996.1_PMC11436996.1.json')
DEST = ROOT/'artifacts/cce_validation/reference_recovery/solid_2024/official_attachments'
NAME = '41467_2024_52560_MOESM1_ESM.pdf'

def main():
    meta = json.loads(INDEX.read_text(encoding='utf-8-sig'))
    assert meta['doi']=='10.1038/s41467-024-52560-7'
    matches = [x for x in meta['media_urls'] if urllib.parse.urlsplit(x).path.endswith('/'+NAME)]
    assert len(matches)==1
    parsed = urllib.parse.urlsplit(matches[0])
    expected = urllib.parse.parse_qs(parsed.query)['md5'][0]
    assert parsed.netloc=='pmc-oa-opendata'
    url = 'https://pmc-oa-opendata.s3.amazonaws.com'+parsed.path
    DEST.mkdir(parents=True,exist_ok=True)
    path=DEST/NAME
    record={'source_url':url,'indexed_uri':matches[0],'index_path':str(INDEX),
            'index_sha256':hashlib.sha256(INDEX.read_bytes()).hexdigest(),'expected_md5':expected,
            'doi':meta['doi'],'pmcid':meta['pmcid'],'license_code':meta['license_code'],
            'new_model_requests':0,'private_payload_sent':False,'authentication_used':False,
            'at_utc':datetime.now(timezone.utc).isoformat(),
            'actual_command':subprocess.list2cmdline([sys.executable,*sys.argv]),
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        if path.exists():
            data=path.read_bytes()
            record['action']='reuse_existing_bytes'
        else:
            req=urllib.request.Request(url,headers={'User-Agent':'ClearEval public OA source verification'})
            with urllib.request.urlopen(req,timeout=25) as response:
                data=response.read(50*1024*1024+1)
                record.update(action='single_public_GET',http_status=response.status,content_type=response.headers.get('Content-Type'),final_url=response.url)
        assert len(data)<=50*1024*1024 and data.startswith(b'%PDF-')
        assert hashlib.md5(data).hexdigest()==expected, 'Indexed original attachment MD5 mismatch'
        if not path.exists():
            path.write_bytes(data)
        record.update(status='recovered_verified_original_bytes_content_review_pending',bytes=len(data),
                      sha256=hashlib.sha256(data).hexdigest(),md5=hashlib.md5(data).hexdigest(),local_path=str(path))
    except Exception as error:
        record.update(status='retrieval_failed',error_type=type(error).__name__,error=str(error))
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    (DEST/f'pmc_object_retrieval_{stamp}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(record,ensure_ascii=True,indent=2))
    return 0 if record['status'].startswith('recovered') else 1

if __name__=='__main__':
    raise SystemExit(main())
