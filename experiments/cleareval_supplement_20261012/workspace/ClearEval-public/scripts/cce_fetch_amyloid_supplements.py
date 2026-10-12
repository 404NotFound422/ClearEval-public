"""Fetch identified public SOLID/CUBIC-HV publisher attachments, without private data."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import io
import json
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/cce_validation/reference_recovery'
PREFIX = 'https://media.springernature.com/original/springer-static/esm/art%3A10.1038%2F'
SOURCES = [('solid_2024', 's41467-024-52560-7', '41467_2024_52560_MOESM1_ESM.pdf'),
           ('cubic_hv_2020', 's41467-020-15906-5', '41467_2020_15906_MOESM1_ESM.pdf'),
           ('cubic_hv_2020', 's41467-020-15906-5', '41467_2020_15906_MOESM4_ESM.xlsx'),
           ('cubic_hv_2020', 's41467-020-15906-5', '41467_2020_15906_MOESM5_ESM.xlsx')]

def obtain(source):
    family, doi_suffix, name = source
    dest = BASE / family / 'official_attachments'
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / name
    url = PREFIX + doi_suffix + '/MediaObjects/' + name
    row = {'public_url': url, 'private_payload_sent': False, 'authentication_used': False,
           'at_utc': datetime.now(timezone.utc).isoformat(), 'new_model_requests': 0,
           'identity': 'exact publisher attachment basename; SOLID publisher media mirror requires content identity verification',
           'command': {'executable': sys.executable, 'argv': [str(Path(__file__).resolve())]}}
    try:
        if path.exists():
            data = path.read_bytes()
            row['action'] = 'reuse_existing_bytes'
        else:
            row['action'] = 'single_public_GET'
            req = urllib.request.Request(url, headers={'User-Agent': 'ClearEval public-source verification'})
            with urllib.request.urlopen(req, timeout=25) as response:
                data = response.read(50*1024*1024+1)
                row.update(http_status=response.status, content_type=response.headers.get('Content-Type'), final_url=response.url)
        if len(data) > 50*1024*1024:
            raise ValueError('50 MiB source size limit')
        if name.endswith('.pdf'):
            valid = data.startswith(b'%PDF-')
        else:
            valid = zipfile.is_zipfile(io.BytesIO(data))
            if valid:
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    valid = 'xl/workbook.xml' in z.namelist()
        if not valid:
            raise ValueError('Expected PDF/XLSX format absent')
        if not path.exists():
            path.write_bytes(data)
        row.update(status='retrieved_format_verified_content_pending', local_path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    except Exception as exc:
        row.update(status='retrieval_failed', error_type=type(exc).__name__, error=str(exc))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    manifest = dest / f'{name}.retrieval_{stamp}.json'
    manifest.write_text(json.dumps(row, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return row

def main():
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(obtain, SOURCES))
    print(json.dumps(rows, ensure_ascii=True, indent=2))
    return 0 if all(r['status'].startswith('retrieved') for r in rows) else 1

if __name__ == '__main__':
    raise SystemExit(main())
