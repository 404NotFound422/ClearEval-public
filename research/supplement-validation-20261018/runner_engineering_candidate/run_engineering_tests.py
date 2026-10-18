#!/usr/bin/env python3
"""Run all original scope tests and package boundaries; missing source is an error."""
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
    source_bound = plan.get('source_bound_tests', plan.get('source_bound_tests_not_run', []))
    declared = set(plan['portable_scope_tests']) | {row['name'] for row in source_bound}
    if available != declared or len(available) != plan['original_scope_test_count']:
        raise ValueError('TEST_PLAN_DOES_NOT_ACCOUNT_FOR_EVERY_ORIGINAL_SCOPE_TEST')
    print('Engineering target: all 18 original scope tests + 3 package-boundary tests.', flush=True)
    print('The 2 source-bound scope tests are included; missing source files are errors.', flush=True)
    suite = loader.loadTestsFromTestCase(scope.ScopeRegressionTests)
    suite.addTests(loader.loadTestsFromTestCase(boundary.PackageBoundaryTests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({'engineering_tests_run': result.testsRun,
        'passed': result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
        'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped),
        'source_bound_tests_included': [item['name'] for item in source_bound],
        'formal_pipeline_validated': False, 'model_calls': 0, 'encoder_calls': 0}, indent=2))
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    raise SystemExit(main())
