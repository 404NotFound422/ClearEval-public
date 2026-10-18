#!/usr/bin/env python3
"""Run the explicitly selected portable suite, reporting source-bound tests not run."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent

def load_file(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def main():
    plan = json.loads((ROOT / 'TEST_PLAN.json').read_text())
    scope = load_file('test_scope_regressions', 'tests/test_scope_regressions.py')
    boundary = load_file('test_package_boundaries', 'tests/test_package_boundaries.py')
    loader = unittest.TestLoader()
    available = set(loader.getTestCaseNames(scope.ScopeRegressionTests))
    selected = plan['portable_scope_tests']
    not_run = plan['source_bound_tests_not_run']
    if available != set(selected) | {row['name'] for row in not_run}:
        raise ValueError('TEST_PLAN_DOES_NOT_ACCOUNT_FOR_EVERY_ORIGINAL_SCOPE_TEST')
    print('Portable target: 16 of 18 original scope tests + 3 package-boundary tests.', flush=True)
    for item in not_run:
        print('NOT RUN (local source evidence required): ' + item['name'], flush=True)
    suite = unittest.TestSuite(scope.ScopeRegressionTests(name) for name in selected)
    suite.addTests(loader.loadTestsFromTestCase(boundary.PackageBoundaryTests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({'portable_tests_run': result.testsRun,
        'passed': result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
        'failures': len(result.failures), 'errors': len(result.errors), 'skipped_in_portable_suite': len(result.skipped),
        'source_bound_tests_not_run': [item['name'] for item in not_run],
        'formal_pipeline_validated': False, 'model_calls': 0, 'encoder_calls': 0}, indent=2))
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    raise SystemExit(main())
