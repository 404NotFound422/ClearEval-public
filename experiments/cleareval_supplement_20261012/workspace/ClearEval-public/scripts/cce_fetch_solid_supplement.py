"""Recover an exact public publisher attachment, with no model/private payload."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'artifacts/cce_validation/reference_recovery/solid_2024/official_attachments'
URL = 'https://static-content.springer-cdn.com/esm/art%3A10.1038%2Fs41467-024-52560-7/MediaObjects/41467_2024_52560_MOESM1_ESM.pdf'
NAME = '41467_2024_52560_MOESM1_ESM.pdf'

def main():
    DEST.mkdir(parents=True, exist_ok=True)
    path = DEST / NAME
    record = {'public_url': URL, 'private_payload_sent': False, 'authentication_used': False,
              'at_utc': datetime.now(timezone.utc).isoformat(), 'new_model_requests': 0,
              'command': {'executable': sys.executable, 'argv': [str(Path(__file__).resolve())]},
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        if path.exists():
            data = path.read_bytes()
            record['action'] = 'reuse_existing_bytes'
        else:
            record['action'] = 'single_public_GET'
            request = urllib.request.Request(URL, headers={'User-Agent': 'ClearEval public-source verification'})
            with urllib.request.urlopen(request, timeout=25) as response:
                data = response.read(40 * 1024 * 1024 + 1)
                record.update(http_status=response.status, final_url=response.url,
                              content_type=response.headers.get('Content-Type'))
        record.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
        if len(data) > 40 * 1024 * 1024:
            raise ValueError('40 MiB source size limit')
        if not data.startswith(b'%PDF-'):
            raise ValueError('Response is not a PDF')
        if not path.exists():
            path.write_bytes(data)
        record.update(status='retrieved_format_verified_content_pending', local_path=str(path))
    except Exception as exc:
        record.update(status='retrieval_failed', error_type=type(exc).__name__, error=str(exc))
    manifest = DEST / 'retrieval_manifest.json'
    i = 1
    while manifest.exists():
        manifest = DEST / f'retrieval_manifest_{i}.json'
        i += 1
    manifest.write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(record, ensure_ascii=True))
    return 0 if record['status'].startswith('retrieved') else 1

if __name__ == '__main__':
    raise SystemExit(main())
