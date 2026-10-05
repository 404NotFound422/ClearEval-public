"""Offline round preparation; caller-supplied builders run beside source data."""
from copy import deepcopy
import importlib
import inspect
import json
from pathlib import Path
import re
import sys
import uuid

from .io import Lock, append, canonical, digest, file_hash, ledger, now, read, save

ROOT = Path(__file__).resolve().parents[2]
CORE = ['evaluator_integrity.py', 'experiments/construct_validity/contract.py',
        'experiments/construct_validity/fidelity.py', 'experiments/construct_validity/evidence.py']
SAFE_ID = re.compile(r'^[A-Za-z0-9_-]{1,100}$')
PRIVATE = {'expected', 'expert_labels', 'gold_labels', 'private_labels', 'reference_labels'}


def callable_at(name):
    module, function = name.split(':', 1)
    value = getattr(importlib.import_module(module), function)
    path = Path(inspect.getsourcefile(value)).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('Builder/processor code must be in the frozen repository')
    return value, path


def load_cases(path=None, builder=None, candidate_dir=None):
    if bool(path) == bool(builder):
        raise ValueError('Supply one public cases file or local builder')
    if builder:
        function, _ = callable_at(builder)
        rows = function(Path(candidate_dir).resolve())
    else:
        path = Path(path)
        rows = (read(path) if path.suffix.lower() == '.json' else
                [json.loads(line) for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip()])
    if isinstance(rows, dict):
        rows = rows.get('cases', [])
    result, ids = [], set()
    for row in rows:
        ident = row['id']
        if not isinstance(ident, str) or not SAFE_ID.fullmatch(ident) or ident in ids:
            raise ValueError('Candidate IDs must be unique safe strings')
        public = deepcopy(row['input'])
        if not isinstance(public, dict) or PRIVATE.intersection(public):
            raise ValueError('Only public input may reach a method')
        if not isinstance(public.get('protocol'), str) or not public['protocol'].strip():
            raise ValueError('A complete candidate text is required')
        reqs = public.get('requirements', [])
        if not isinstance(reqs, list) or (not reqs and not public.get('requested_fields')):
            raise ValueError('Explicit requirements or requested extraction fields are required')
        if public.get('requested_fields') and not all(isinstance(field, str) for field in public['requested_fields']):
            raise ValueError('Requested fields must be explicit names')
        req_ids = [req['id'] for req in reqs]
        if len(set(req_ids)) != len(req_ids) or any(not isinstance(key, str) for key in req_ids):
            raise ValueError('Requirement identities must be explicit and unique')
        if row.get('input_sha256') not in (None, digest(public)):
            raise ValueError('Public input SHA mismatch')
        result.append({'id': ident, 'task_id': row.get('task_id', ident),
                       'input': public, 'input_sha256': digest(public)})
        ids.add(ident)
    if not result:
        raise ValueError('No candidates')
    return result


def validate_judges(judges):
    allowed = {'id', 'role', 'transport', 'family', 'model', 'revision', 'params',
               'base_url', 'timeout_seconds', 'parameters_disclosure'}
    ids = set()
    for judge in judges:
        if set(judge) - allowed:
            raise ValueError('Public judge configs contain unknown/private fields')
        if not SAFE_ID.fullmatch(judge['id']) or judge['id'] in ids:
            raise ValueError('Judge identities must be unique and safe')
        if judge.get('role') != 'TEACHER':
            raise ValueError('A generation model is not a teacher comparison')
        if judge.get('transport') not in ('OLLAMA_LOOPBACK', 'EXTERNAL_ACTUAL'):
            raise ValueError('Only local loopback or explicitly imported actual calls are supported')
        if not judge.get('family') or not judge.get('model'):
            raise ValueError('Teacher family/model must be declared')
        revision = judge.get('revision', 'UNKNOWN')
        if revision != 'UNKNOWN' and not re.fullmatch('[a-fA-F0-9]{64}', revision):
            raise ValueError('Exact revision digest or UNKNOWN required')
        judge['revision'] = revision
        if judge['transport'] == 'OLLAMA_LOOPBACK':
            params = judge.get('params')
            if not isinstance(params, dict) or not all(key in params for key in ('temperature', 'seed', 'num_ctx', 'num_predict')):
                raise ValueError('Declare temperature, seed, context and output budgets')
            if params['num_predict'] <= 0 or params['num_ctx'] <= 0:
                raise ValueError('Context/output token limits must be positive')
        else:
            judge.setdefault('params', None)
            judge.setdefault('parameters_disclosure', 'UNAVAILABLE')
        ids.add(judge['id'])
    if not ids:
        raise ValueError('No teachers')


def prepare(study, *, cases, judges, prompt, label, repeats=3, processors=None, builder=None, code_paths=None, prompt_builder=None, dependencies=None):
    if isinstance(repeats, bool) or not isinstance(repeats, int) or repeats < 3:
        raise ValueError('At least three independent planned repetitions are required')
    for case in cases:
        if case.get('input_sha256') != digest(case['input']):
            raise ValueError('Prepared public case SHA mismatch')
    study = Path(study).resolve()
    study.mkdir(parents=True, exist_ok=True)
    judges = deepcopy(judges)
    validate_judges(judges)
    processors = deepcopy(processors or [{'id': 'core_guard', 'entrypoint': None}])
    if any(not SAFE_ID.fullmatch(p['id']) for p in processors):
        raise ValueError('Unsafe processor identity')
    if len({p['id'] for p in processors}) != len(processors):
        raise ValueError('Duplicate processor identity')
    with Lock(study / '.prepare_lock'):
        previous = ledger(study / 'rounds.jsonl')
        if len(previous) >= 8:
            raise ValueError('Eight-round maximum reached')
        round_id = f'r{len(previous) + 1:02d}-{uuid.uuid4().hex[:8]}'
        folder = study / round_id
        folder.mkdir()
        save(folder / 'cases.json', cases)
        save(folder / 'judges.json', judges)
        save(folder / 'processors.json', processors)
        (folder / 'prompt.txt').write_bytes(prompt.encode('utf-8'))
        paths = list(Path(__file__).parent.glob('*.py')) + [ROOT / key for key in CORE]
        declared_dependencies = list(dependencies or [])
        for entry in [builder, prompt_builder, *(p.get('entrypoint') for p in processors)]:
            if entry:
                function, code_path = callable_at(entry)
                paths.append(code_path)
                declaration = getattr(importlib.import_module(function.__module__), 'DEPENDENCIES', [])
                if not isinstance(declaration, (list, tuple)):
                    raise ValueError('Module DEPENDENCIES must explicitly list files/directories')
                declared_dependencies.extend(declaration)
        for name in code_paths or []:
            path = (ROOT / name).resolve()
            if not path.is_relative_to(ROOT) or path.suffix != '.py':
                raise ValueError('Extra frozen code must be repository Python source')
            paths.append(path)
        for name in declared_dependencies:
            target = (ROOT / name).resolve()
            if not target.is_relative_to(ROOT) or target == ROOT:
                raise ValueError('Dependencies must name a bounded repository file/directory')
            candidates = [target] if target.is_file() else [p for p in target.rglob('*') if p.is_file()]
            if not candidates:
                raise ValueError('Declared dependency does not exist or is empty')
            for dependency in candidates:
                dependency = dependency.resolve()
                if not dependency.is_relative_to(ROOT):
                    raise ValueError('Dependency symlink escapes the repository')
                paths.append(dependency)
        code = {path.relative_to(ROOT).as_posix(): file_hash(path) for path in paths}
        trials = []
        for case in cases:
            if prompt_builder:
                render, _ = callable_at(prompt_builder)
                rendered = render(deepcopy(case['input']))
                if not isinstance(rendered, str) or not rendered.strip():
                    raise ValueError('Server prompt builder must return the actual nonempty prompt')
            else:
                rendered = prompt + '\n\nPUBLIC_INPUT_JSON\n' + canonical(case['input'])
            prompt_path = folder / 'prompts' / f"{case['id']}.txt"
            prompt_path.parent.mkdir(exist_ok=True)
            prompt_path.write_bytes(rendered.encode('utf-8'))
            for judge in judges:
                for repeat in range(1, repeats + 1):
                    trials.append({'id': f"{case['id']}__{judge['id']}__r{repeat:02d}",
                        'candidate_id': case['id'], 'judge_id': judge['id'], 'repeat_id': repeat,
                        'input_sha256': case['input_sha256'], 'prompt_sha256': file_hash(prompt_path)})
        save(folder / 'trials.json', trials)
        files = {path.relative_to(folder).as_posix(): file_hash(path)
                 for path in folder.rglob('*') if path.is_file()}
        manifest = {'schema': 'evaluator-experiment-v2', 'round_id': round_id,
            'round_index': len(previous) + 1, 'label': label, 'created_at': now(),
            'repeats': repeats, 'planned_trials': len(trials), 'files': files, 'code': code,
            'declared_dependencies': sorted(set(str(name) for name in declared_dependencies)),
            'builder': builder, 'prompt_builder': prompt_builder, 'previous_round_event': previous[-1]['event_sha256'] if previous else None,
            'python': sys.version, 'scientific_labels': 'SEPARATE_NOT_READ_BY_RUNNER'}
        manifest['manifest_sha256'] = digest(manifest)
        save(folder / 'manifest.json', manifest)
        append(study / 'rounds.jsonl', {'kind': 'ROUND_PREPARED', 'round_id': round_id,
            'manifest_sha256': manifest['manifest_sha256'], 'created_at': now()})
    return folder


def verify(folder):
    folder = Path(folder).resolve()
    manifest = read(folder / 'manifest.json')
    if manifest['manifest_sha256'] != digest({k: v for k, v in manifest.items() if k != 'manifest_sha256'}):
        raise ValueError('Manifest checksum mismatch')
    for name, expected in manifest['files'].items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder) or file_hash(path) != expected:
            raise ValueError('Frozen round input changed; create a new round')
    for name, expected in manifest['code'].items():
        if file_hash(ROOT / name) != expected:
            raise ValueError('Executing source changed; create a new round')
    return manifest