"""Read two explicitly identified public PMC attachments; no model or private payload."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import argparse
import io
import json
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'artifacts/cce_validation/reference_recovery/idisco_plus_2016/official_attachments'
FILES = ['NIHMS784827-supplement-8.pdf', 'NIHMS784827-supplement-9.docx']
MAX_BYTES = 20 * 1024 * 1024


def obtain(filename):
    path = DEST / filename
    url = URLS[filename]
    row = {'filename': filename, 'public_url': url, 'private_payload_sent': False,
           'authentication_used': False, 'at_utc': datetime.now(timezone.utc).isoformat()}
    if path.exists():
        data = path.read_bytes()
        row['action'] = 'reuse_existing_bytes'
    else:
        row['action'] = 'single_public_GET'
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'ClearEval public-source verification'})
            with urllib.request.urlopen(request, timeout=25) as response:
                data = response.read(MAX_BYTES + 1)
                row.update(http_status=response.status, content_type=response.headers.get('Content-Type'),
                           final_url=response.url)
        except Exception as exc:
            row.update(status='retrieval_failed', error_type=type(exc).__name__, error=str(exc))
            return row
    row.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    if len(data) > MAX_BYTES:
        row['status'] = 'stopped_size_limit'
        return row
    valid = data.startswith(b'%PDF-') if filename.endswith('.pdf') else zipfile.is_zipfile(io.BytesIO(data))
    if valid and filename.endswith('.docx'):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            valid = 'word/document.xml' in z.namelist()
    row['expected_format_present'] = valid
    if valid:
        path.write_bytes(data)
        row.update(status='retrieved_format_verified_content_pending', local_path=str(path))
    else:
        diagnostic = DEST / (filename + '.unexpected_response.bin')
        diagnostic.write_bytes(data)
        row.update(status='unexpected_response_not_source', diagnostic_path=str(diagnostic))
    return row


def main():
    global DEST, FILES, URLS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publisher', action='store_true', help='Use publisher attachment candidates for the verified article PII; never retry PMC endpoints.')
    args = parser.parse_args()
    if args.publisher:
        DEST = DEST.parent / 'publisher_attachments'
        FILES = ['1-s2.0-S0092867416305554-mmc8.pdf', '1-s2.0-S0092867416305554-mmc9.docx']
        URLS = {f: 'https://ars.els-cdn.com/content/image/' + f for f in FILES}
    else:
        URLS = {f: 'https://pmc.ncbi.nlm.nih.gov/articles/PMC4912438/bin/' + f for f in FILES}
    DEST.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(obtain, FILES))
    payload = {'records': records, 'model_requests': 0, 'scope': 'two_public_source_attachments_only',
               'attachment_identity': 'publisher PII candidate paths; source content verification required' if args.publisher else 'exact filenames from local author-manuscript XML',
               'command': {'executable': sys.executable, 'argv': [str(Path(__file__).resolve()), *sys.argv[1:]]}}
    manifest = DEST / 'retrieval_manifest.json'
    if manifest.exists():
        # Preserve previous attempts instead of concealing failures or overwriting provenance.
        number = 1
        while (DEST / f'retrieval_manifest_{number}.json').exists():
            number += 1
        manifest = DEST / f'retrieval_manifest_{number}.json'
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'manifest': str(manifest), 'records': records}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
