"""Archive-free package boundary checks; no model/encoder or scientific test data."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import runner as R
import verify_package

class PackageBoundaryTests(unittest.TestCase):
    def test_original_vendor_hashes_and_declared_missing_files(self):
        report = verify_package.check()
        self.assertEqual(report['package_status'], 'PASS')
        self.assertEqual(report['vendor_files_missing'], report['expected_vendor_omissions'])
        self.assertEqual(report['vendor_snapshot_complete'], report['expected_vendor_omissions'] == 0)
        self.assertFalse(report['formal_pipeline_validated'])
        provenance = json.loads((ROOT / 'PROVENANCE.json').read_text())
        self.assertEqual(R.sha(ROOT / 'VENDOR_MANIFEST.json'), provenance['source_vendor_manifest_sha256'])
        self.assertEqual(R.code_freeze(), provenance['source_code_freeze'])

    def test_prepare_still_rejects_missing_vendor_before_output(self):
        # Exercise the unchanged real vendor guard against an intentionally empty
        # temporary source root, even when this delivered snapshot is complete.
        with tempfile.TemporaryDirectory() as temp:
            partial_root = Path(temp) / 'incomplete_candidate'
            partial_root.mkdir()
            (partial_root / 'VENDOR_MANIFEST.json').write_bytes((ROOT / 'VENDOR_MANIFEST.json').read_bytes())
            output = Path(temp) / 'must_remain_absent'
            with patch.object(R, 'HERE', partial_root):
                with self.assertRaises(FileNotFoundError):
                    R.prepare(Path(temp) / 'no_execution_manifest.json', output)
            self.assertFalse(output.exists())

    def test_all_cli_help_without_site_packages(self):
        env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')}
        commands = [('runner.py', []), ('build_input_bindings.py', [])]
        commands.extend(('runner.py', [cmd]) for cmd in ('inventory-check', 'prepare', 'verify', 'execute'))
        for filename, args in commands:
            with self.subTest(filename=filename, args=args):
                result = subprocess.run([sys.executable, '-S', '-B', str(ROOT / filename), *args, '--help'],
                    cwd=ROOT, env=env, text=True, capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('usage:', result.stdout)

if __name__ == '__main__':
    unittest.main()
