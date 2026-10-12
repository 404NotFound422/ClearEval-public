"""Frozen offline numerical analysis of all sixteen committed Codex assessments.

Reads only primary-released anonymous records after the controller's release
gate. It neither dispatches agents nor reads sealed inputs or the identity key.
"""
from __future__ import annotations
from collections import Counter
import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
import socket
import statistics
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_blind_subagent_confirmation_v1 as controller
import cce_grounded_offline_scoring_v1 as scoring

require = controller.require
METRICS = scoring.METRICS
GROUPS = {'direct_judge': scoring.DIRECT, 'computed_EGES': scoring.EGES,
    'deterministic_steps': ['sr', 'sp'], 'derived_CCE': ['Com', 'Cor', 'Eff', 'IA', 'HV']}


def definition():
    return {'status': 'prospective_analysis_definition', 'answers': 8,
        'codex_replicates': 2, 'planned_observations': 16,
        'codex_paired_metric_slots': 128, 'codex_vs_primary_metric_slots': 512,
        'independent_answer_n': 8, 'metrics_are_independent_samples': False,
        'categories': GROUPS, 'tolerance': scoring.TOL,
        'missing': 'No imputation. Preserve verified deterministic SR/SP after judge failure.',
        'comparison': 'All same-answer pairs, including missing values; compare means only on stated common numeric answer sets.',
        'model_sources': 'Two primary local families plus two Codex replicates; Codex backend identity unknown.',
        'new_model_calls_in_analysis': 0, 'expert_truth': False, 'formal_eligible': False,
        'numeric_definition': scoring.definition()}


def category(metric):
    return next(name for name, metrics in GROUPS.items() if metric in metrics)


def paired_rows(left, right, label):
    rows = []
    for metric in METRICS:
        a, b = left['metrics'][metric], right['metrics'][metric]
        valid = scoring.finite(a) and scoring.finite(b)
        delta = b - a if valid else None
        rows.append({'anonymous_answer_id': left['anonymous_answer_id'],
            'comparison': label, 'left_id': left['observation_id'], 'right_id': right['observation_id'],
            'metric': metric, 'category': category(metric), 'left': a, 'right': b,
            'both_finite': valid, 'right_minus_left': delta,
            'different': abs(delta) > scoring.TOL if valid else None,
            'fixed_steps_are_new_judge_observations': False,
            'counts_as_direct_judge_difference': metric in scoring.DIRECT})
    return rows


def summarize(observations, primary):
    ids = {f'C{i:02}' for i in range(1, 9)}
    require(len(observations) == 16 and {(r['anonymous_answer_id'], r['replicate']) for r in observations} ==
        {(aid, repeat) for aid in ids for repeat in [1, 2]}, 'ALL_SIXTEEN_CODEX_CELLS_REQUIRED')
    require(len(primary) == 16 and {r['anonymous_answer_id'] for r in primary} == ids,
        'ALL_SIXTEEN_PRIMARY_CELLS_REQUIRED')
    judges = sorted({r['judge'] for r in primary})
    require(len(judges) == 2 and {(r['anonymous_answer_id'], r['judge']) for r in primary} ==
        {(aid, judge) for aid in ids for judge in judges}, 'PRIMARY_TWO_JUDGE_GRID_REQUIRED')
    within, cross = [], []
    for aid in sorted(ids):
        codex = sorted((r for r in observations if r['anonymous_answer_id'] == aid), key=lambda r: r['replicate'])
        within += paired_rows(codex[0], codex[1], 'codex_replicate_2_minus_1')
        for p in (r for r in primary if r['anonymous_answer_id'] == aid):
            p = {**p, 'observation_id': p['trial_id']}
            for c in codex:
                cross += paired_rows(p, c, 'codex_minus_' + p['judge'])
    require(len(within) == 128 and len(cross) == 512, 'PAIRED_METRIC_DENOMINATORS_CHANGED')
    summaries = []
    for label, rows in [('codex_replicates', within), ('codex_vs_primary', cross)]:
        for group in GROUPS:
            subset = [r for r in rows if r['category'] == group]
            finite = [r for r in subset if r['both_finite']]
            summaries.append({'comparison': label, 'category': group, 'planned_metric_pairs': len(subset),
                'finite_metric_pairs': len(finite), 'missing_metric_pairs': len(subset) - len(finite),
                'different_metric_pairs': sum(r['different'] for r in finite),
                'mean_absolute_difference': statistics.mean(abs(r['right_minus_left']) for r in finite) if finite else None,
                'max_absolute_difference': max(abs(r['right_minus_left']) for r in finite) if finite else None,
                'agreement_is_not_correctness': True})
    return {'codex_repeat_pairs': within, 'primary_comparison_pairs': cross, 'category_summary': summaries}


@contextlib.contextmanager
def no_network():
    old_socket, old_connection = socket.socket.connect, socket.create_connection
    def denied(*args, **kwargs):
        raise RuntimeError('NETWORK_FORBIDDEN_IN_OFFLINE_BLIND_ANALYSIS')
    socket.socket.connect = denied
    socket.create_connection = denied
    try:
        yield
    finally:
        socket.socket.connect, socket.create_connection = old_socket, old_connection


def module_from(path):
    spec = importlib.util.spec_from_file_location('blind_selected_development_backend', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def table(out, name, rows):
    controller.write(out / (name + '.json'), rows)
    if rows:
        fields = list(dict.fromkeys(key for row in rows for key in row))
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: controller.canonical(value) if isinstance(value, (dict, list)) else value for key, value in row.items()})
        (out / (name + '.csv')).write_text(stream.getvalue(), encoding='utf-8-sig')


def verify_committed_return(directory, cell, terminal, terminal_event, events):
    """Bind preserved return bytes to the write-once terminal and root receipt.

    A current raw/commit/conversion trio is insufficient: its raw hash must
    still equal the hash committed in the terminal and append-only event.
    Failed returns receive the same identity checks as successful returns.
    """
    require(terminal.get('cell_id') == cell['cell_id'] and terminal.get('attempt') == 1,
        'TERMINAL_CELL_OR_ATTEMPT_MISMATCH')
    if cell['status'] not in ['success', 'failed']:
        require(terminal.get('raw_sha256') is None and terminal_event.get('raw_sha256') is None and
            not any((directory / name).exists() for name in
                ['raw_response.txt', 'raw_commit.json', 'actual_return_evidence.json']),
            'NO_RETURN_TERMINAL_HAS_RETURN_ARTIFACTS')
        return None
    raw = (directory / 'raw_response.txt').read_bytes()
    digest = controller.rawsha(raw)
    commit = controller.read(directory / 'raw_commit.json')
    require(commit.get('raw_sha256') == digest and commit.get('raw_file_sha256') == digest and
        terminal.get('raw_sha256') == digest and terminal_event.get('raw_sha256') == digest,
        'COMMITTED_RETURN_RAW_IDENTITY_MISMATCH')
    require(commit.get('raw_byte_length') == len(raw) and commit.get('parsing_started_after_commit') is True,
        'RAW_COMMIT_METADATA_MISMATCH')
    evidence_path = directory / 'actual_return_evidence.json'
    require(terminal.get('actual_return_evidence') == controller.bind(evidence_path),
        'COMMITTED_RETURN_EVIDENCE_BINDING_MISMATCH')
    evidence = controller.read(controller.verify(terminal['actual_return_evidence']))
    require(evidence.get('recorded_by') == 'root_agent' and
        evidence.get('event') == 'actual_subagent_final_response' and
        evidence.get('cell_id') == cell['cell_id'] and evidence.get('raw_sha256') == digest and
        evidence.get('root_edited') is False and evidence.get('response_kind') == 'final' and
        bool(evidence.get('actual_tool_receipt')), 'COMMITTED_RETURN_RECEIPT_MISMATCH')
    dispatch = [event for event in events if event.get('cell_id') == cell['cell_id'] and
        event.get('event') == 'assessment_dispatched']
    require(len(dispatch) == 1 and cell['actual_dispatched'] is True and
        bool(dispatch[0].get('agent_id')) and evidence.get('actual_agent_id') == dispatch[0]['agent_id'],
        'COMMITTED_RETURN_AGENT_MISMATCH')
    return raw


def analyze():
    with no_network():
        _, paths, matrix = controller.prepared()
        require(paths['numeric_adapter'].resolve() == Path(scoring.__file__).resolve() and
            paths['numeric_analyzer'].resolve() == Path(__file__).resolve(), 'FROZEN_NUMERIC_CODE_PATH_MISMATCH')
        before = controller.PRIMARY_LEDGER.read_bytes()
        events = controller.rows(controller.external_ledger())
        external_before = controller.external_ledger().read_bytes()
        states = controller.status_rows(matrix, events)
        require(all(r['status'] in ['success', 'failed', 'missing_response', 'dispatch_not_started'] for r in states), 'BLIND_BATCH_NOT_ALL_TERMINAL')
        records = {r['anonymous_answer_id']: r for r in controller.read(paths['blind_inputs'])}
        steps = controller.read(paths['deterministic_steps'])
        require(len(steps) == 8 and len({r['anonymous_answer_id'] for r in steps}) == 8, 'STEP_EIGHT_ANSWERS_REQUIRED')
        steps = {r['anonymous_answer_id']: r for r in steps}
        step_verification = controller.read(paths['step_verification'])
        require(step_verification.get('status') == 'pass' and step_verification.get('original_SR_SP') is True and
            step_verification.get('primary_threshold') == .7 and
            str(step_verification.get('encoder', '')).endswith('all-mpnet-base-v2'), 'ORIGINAL_STEP_POLICY_UNVERIFIED')
        require(bool(step_verification.get('bindings')), 'STEP_SOURCE_BINDINGS_REQUIRED')
        for item in step_verification['bindings']:
            controller.verify(item)
        backend = module_from(paths['development_backend'])
        require(Path(backend.grounded.__file__).resolve() == paths['converter'].resolve(), 'BACKEND_CONVERTER_MISMATCH')
        require(backend.grounded.schema() == controller.read(paths['schema']), 'BACKEND_SCHEMA_MISMATCH')
        bindings = [controller.bind(path) for path in paths.values()]
        observations, replays = [], {}
        for cell in states:
            aid = cell['anonymous_answer_id']
            record, step = records[aid], steps[aid]
            case = controller.clean_record(record)
            require(step['source_id'] == backend.grounded.source_id_for_case(case) and
                step['answer_sha256'] == controller.rawsha(case['model_response']) and
                step['question_sha256'] == controller.rawsha(case['specific_question']) and
                step['references_sha256'] == controller.rawsha(controller.canonical(case['references'])), 'STEP_FULL_INPUT_BINDING_MISMATCH')
            directory = controller.OUT / 'observations' / cell['cell_id']
            terminal_path = directory / 'terminal.json'
            terminal = controller.read(terminal_path)
            matching = [event for event in events if event.get('cell_id') == cell['cell_id'] and event['event'] == 'assessment_terminal']
            require(len(matching) == 1 and matching[0]['terminal'] == controller.bind(terminal_path) and
                terminal['status'] == cell['status'], 'TERMINAL_LEDGER_BINDING_MISMATCH')
            raw = verify_committed_return(directory, cell, terminal, matching[0], events)
            numeric = None
            failure = None
            values = scoring.derive({}, step, False)
            if cell['status'] == 'success':
                doc = controller.read(controller.OUT / 'packets' / cell['cell_id'] / 'source_document.json')
                conversion = backend.grounded.convert(raw.decode('utf8'), doc)
                require(conversion == controller.read(directory / 'conversion.json'), 'FROZEN_RAW_CONVERSION_REPLAY_MISMATCH')
                try:
                    numeric = scoring.score_conversion(case, conversion, backend, step)
                    values = numeric['metrics']
                except Exception as exc:
                    failure = {'type': type(exc).__name__, 'message': str(exc)}
                replays[cell['cell_id']] = {'numeric': numeric, 'numeric_failure': failure}
            observations.append({'observation_id': cell['cell_id'], 'anonymous_answer_id': aid,
                'replicate': cell['replicate'], 'status': cell['status'],
                'actual_dispatched': cell['actual_dispatched'],
                'numeric_status': 'replayed' if numeric else 'failed' if failure else 'unavailable_after_terminal_failure',
                'numeric_failure': failure, 'metrics': values,
                'complete_numeric_CCE': bool(numeric and numeric['complete_numeric_CCE']),
                'backend_identity': 'unknown', 'source_kind': 'Codex subagent model-generated assessment',
                'expert_return': False, 'formal_eligible': False})
            bindings += [controller.bind(path) for path in sorted(directory.iterdir()) if path.is_file()]
        primary = controller.read(paths['primary_observations'])
        comparisons = summarize(observations, primary)
        require(controller.PRIMARY_LEDGER.read_bytes() == before and
            controller.external_ledger().read_bytes() == external_before, 'OFFLINE_ANALYSIS_CHANGED_REQUEST_LEDGER')
        out = controller.OUT / 'analysis'
        require(not (out / 'verification.json').exists(), 'FINAL_ANALYSIS_ALREADY_EXISTS_NO_REPLACEMENT')
        out.mkdir(exist_ok=True)
        controller.write(out / 'definition.json', definition())
        controller.write(out / 'numeric_replays.json', replays)
        table(out, 'observations', observations)
        for name, rows in comparisons.items():
            table(out, name, rows)
        summary = {'status': 'complete_descriptive_model_source_analysis_not_validation',
            'planned_assessments': 16, 'answers': 8, 'replicates': 2,
            'actual_dispatched': sum(r['actual_dispatched'] for r in observations),
            'technical_status_counts': dict(Counter(r['status'] for r in observations)),
            'numeric_status_counts': dict(Counter(r['numeric_status'] for r in observations)),
            'complete_numeric_CCE': sum(r['complete_numeric_CCE'] for r in observations),
            'expert_returns': 0, 'verified_distinct_codex_families': False,
            'new_analysis_model_requests': 0, 'new_analysis_external_assessments': 0,
            'claim_limit': 'Differences and source-supported projections are model diagnostics, not expert accuracy.',
            'all16_cells_retained': True}
        controller.write(out / 'summary.json', summary)
        output_bindings = [controller.bind(path) for path in sorted(out.iterdir()) if path.is_file()]
        controller.write(out / 'verification.json', {'status': 'pass',
            'scope': 'Bound observations, original formula replay or explicit numerical failure, and fixed pair denominators',
            'scientific_correctness_proven': False, 'all_16_terminal_cells_retained': True,
            'codex_paired_metric_slots': 128, 'primary_comparison_metric_slots': 512,
            'inputs': bindings, 'outputs': output_bindings, 'actual_command': [sys.executable, *sys.argv],
            'new_model_requests': 0})
        print(json.dumps(summary))


if __name__ == '__main__':
    analyze()
