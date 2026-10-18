"""Opt-in SR pipeline: one canonical assessment, then a score-only proposal.

No model invocation is performed by this module except through the supplied
provider callback. Recorded fixtures exercise this boundary without an LLM run.
The canonical extraction schema is never extended with numerical score fields.
"""
from copy import copy, deepcopy
import asyncio
import json
import math
import os
from pathlib import Path
import re
import subprocess

from evaluation_contract import json_hash, sha256_file
from oeq_ri_reference import ri_reference_policy
from evaluator_integrity import parse_judge_object
from experiments.construct_validity.fidelity import text_hash
from oeq_scientific import apply_assessment, build_context, _route_method_identity

VERSION = 'oeq-sr-assessment-continuous-v8-range-midpoint'
ROOT = Path(__file__).resolve().parent


class SRSetupError(ValueError):
    """No candidate judgments were run because fixed grading inputs are absent."""
    failure_stage = 'SR_INPUT_SETUP_UNAVAILABLE'

    def __init__(self, failures, question_ids):
        self.failures = deepcopy(failures)
        self.not_run_question_ids = list(question_ids)
        self.n_not_run = len(self.not_run_question_ids)
        super().__init__('SR input setup unavailable; no judge calls made: ' +
                         '; '.join(str(row['question_id']) + ': ' + row['reason'] for row in failures))


def output_schema(stage):
    """Distinct closed output contracts, never inject scores into canonical JSON."""
    import json
    if stage == 'canonical':
        from experiments.construct_validity.compact_grounding import SCHEMA
        schema = json.loads((ROOT / 'prompts/oeq_record_output.schema.json').read_text(encoding='utf-8'))
        extraction_schema = schema['properties']['extraction']
        if extraction_schema.get('$ref') == '#/$defs/extraction':
            extraction_schema = schema['$defs']['extraction']
        extraction_schema['properties']['schema_version']['const'] = SCHEMA
        return schema
    if stage != 'score_only':
        raise ValueError('Unknown SR assessment stage')
    from oeq_sr_scoring import score_only_output_schema
    return score_only_output_schema()


def _stage_model(teacher_model, stage):
    # The Ollama adapter owns a per-instance format option. A shallow copy shares
    # its client but never mutates the model used by concurrent question jobs.
    # Other adapters continue using their existing JSON prompt/parser boundary.
    if hasattr(teacher_model, 'format'):
        model = copy(teacher_model)
        model.format = output_schema(stage)
        return model
    return teacher_model


def select_sr_input(inputs, question, protocol, *, encoder_config=None):
    """Require a frozen per-answer matching input; never synthesize a matrix."""
    if not isinstance(inputs, dict):
        raise ValueError('SR inputs must map question IDs to frozen answer-bound objects')
    value = inputs.get(str(question['question_id']))
    if not isinstance(value, dict):
        raise ValueError('Selected question lacks explicit SR step inputs')
    if value.get('question_sha256') != json_hash(question):
        raise ValueError('SR step inputs belong to another question or protocol')
    expected_protocol = value.get('protocol_sha256')
    if (expected_protocol != text_hash(protocol) and
            (encoder_config is None or expected_protocol is not None)):
        raise ValueError('SR step inputs belong to another question or protocol')
    if 'selected_route' not in value or (value['selected_route'] is not None and
            (not isinstance(value['selected_route'], str) or not value['selected_route'].strip())):
        raise ValueError('selected_route must be an explicit nonempty string or null')
    if encoder_config is None:
        if not isinstance(value.get('step_request'), dict):
            raise ValueError('SR step_request must be explicitly supplied')
    elif value.get('step_request') is not None:
        raise ValueError('Live pinned encoder mode cannot also supply a recorded step_request')
    else:
        value = {**value, 'step_request': None}
    return deepcopy(value)


def pinned_encoder_config(python_path, script_path, revision):
    """Freeze an explicitly selected installed local provider; never download."""
    if not isinstance(revision, str) or not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('Pinned encoder revision must be a full immutable 40-character commit')
    python, script = Path(python_path).absolute(), Path(script_path).resolve()
    if not python.is_file() or not script.is_file():
        raise ValueError('Pinned encoder Python and script must already exist locally')
    manifest = script.parent / 'artifacts/model_manifest.json'
    lock = script.parent / 'requirements.lock.txt'
    if not manifest.is_file() or not lock.is_file():
        raise ValueError('Pinned encoder requires its verified model manifest and package lock')
    weights_sha = None
    if manifest.is_file():
        frozen = parse_judge_object(manifest.read_text(encoding='utf-8'))
        if frozen.get('model_id') != 'sentence-transformers/all-mpnet-base-v2' or frozen.get('revision') != revision:
            raise ValueError('Model manifest differs from configured MPNet identity/revision')
        weights = [row for row in frozen.get('files', []) if row.get('path') == 'model.safetensors']
        if (len(weights) != 1 or not isinstance(weights[0].get('sha256'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', weights[0]['sha256'])
                or weights[0]['sha256'] != weights[0].get('official_lfs_sha256')):
            raise ValueError('Pinned MPNet weights lack matching official LFS hash evidence')
        weights_sha = weights[0]['sha256']
    snapshot = Path(frozen.get('snapshot_path', ''))
    if not snapshot.is_dir():
        raise ValueError('Pinned model snapshot directory is unavailable')
    verified_files = []
    for row in frozen.get('files', []):
        relative = Path(row.get('path', ''))
        if (not row.get('path') or relative.is_absolute() or '..' in relative.parts
                or not re.fullmatch(r'[0-9a-f]{64}', str(row.get('sha256', '')))):
            raise ValueError('Invalid pinned model file manifest entry')
        file = snapshot / relative
        if (not file.is_file() or file.stat().st_size != row.get('bytes')
                or sha256_file(file) != row['sha256']):
            raise ValueError('Pinned model artifact bytes changed: ' + row['path'])
        verified_files.append({'path': row['path'], 'bytes': row['bytes'], 'sha256': row['sha256']})
    expected_packages = {}
    for line in lock.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if not re.fullmatch(r'[A-Za-z0-9_.-]+==[^\s;]+', line):
            raise ValueError('Encoder package lock must contain exact installed-version pins')
        name, version = line.split('==', 1)
        expected_packages[name] = version
    if not expected_packages:
        raise ValueError('Encoder package lock is empty')
    code = ('import importlib.metadata as m,json,platform,sys; '
            'names=json.loads(sys.argv[1]); '
            'print(json.dumps({"python":platform.python_version(),'
            '"packages":{name:m.version(name) for name in names}},sort_keys=True))')
    checked = subprocess.run([str(python), '-c', code, json.dumps(list(expected_packages))],
                             capture_output=True, text=True, timeout=60, check=False)
    if checked.returncode:
        raise ValueError('Cannot verify the installed pinned encoder package versions')
    installed = parse_judge_object(checked.stdout)
    if installed.get('packages') != expected_packages:
        raise ValueError('Installed encoder packages differ from the frozen lock')
    return {'schema_version': 'local-pinned-mpnet-provider-continuous-v2',
            'python': str(python), 'script': str(script), 'script_sha256': sha256_file(script),
            'model_id': 'sentence-transformers/all-mpnet-base-v2', 'revision': revision,
            'model_manifest_sha256': sha256_file(manifest) if manifest.is_file() else None,
            'model_manifest_path': str(manifest) if manifest.is_file() else None,
            'model_weights_sha256': weights_sha,
            'package_lock_sha256': sha256_file(lock),
            'verified_model_files': verified_files, 'package_versions': expected_packages,
            'python_version': installed['python'],
            'offline': True, 'matching_contract': 'independent_row_column_maxima_raw_cosine_mean', 'timeout_seconds': 600}


def _check_encoder_config(config):
    if (not isinstance(config, dict) or config.get('schema_version') != 'local-pinned-mpnet-provider-continuous-v2'
            or config.get('offline') is not True):
        raise ValueError('A frozen offline MPNet provider configuration is required')
    if pinned_encoder_config(config['python'], config['script'], config['revision']) != config:
        raise ValueError('Pinned encoder provider files or configuration changed')


async def run_pinned_encoder(config, texts):
    """One actual local subprocess request with no shell and offline model flags."""
    _check_encoder_config(config)
    if not isinstance(texts, list) or not texts or any(not isinstance(t, str) for t in texts):
        raise ValueError('Encoder input must be a nonempty ordered text array')
    environment = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                       HF_HUB_DISABLE_TELEMETRY='1', TOKENIZERS_PARALLELISM='false')
    process = await asyncio.create_subprocess_exec(config['python'], config['script'],
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, env=environment)
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(
            json.dumps({'texts': texts}, ensure_ascii=False).encode('utf-8')),
            timeout=config['timeout_seconds'])
    except (asyncio.TimeoutError, asyncio.CancelledError):
        process.kill()
        await process.wait()
        raise
    if process.returncode != 0:
        raise ValueError('Pinned encoder failed (exit ' + str(process.returncode) + '): ' +
                         stderr.decode('utf-8', errors='replace')[-4000:])
    if len(stdout) > 64 * 1024 * 1024:
        raise ValueError('Pinned encoder result exceeded the 64 MiB contract')
    return parse_judge_object(stdout.decode('utf-8'))


def _validate_encoder_output(result, texts, config):
    if not isinstance(result, dict) or result.get('texts') != texts:
        raise ValueError('Encoder output text/order differs from actual canonical/reference inputs')
    if result.get('ordered_texts_sha256') != json_hash(texts):
        raise ValueError('Encoder ordered-text hash mismatch')
    runtime = result.get('runtime', {})
    expected = {'model_id': config['model_id'], 'model_revision': config['revision'],
                'dtype': 'float32', 'normalization': 'L2', 'dimensions': 768,
                'max_seq_length': 384, 'device': 'cpu'}
    expected['encoder_script_sha256'] = config['script_sha256']
    for key in ('model_weights_sha256', 'package_lock_sha256'):
        if config.get(key) is not None:
            expected[key] = config[key]
    expected['python'] = config['python_version']
    if any(runtime.get(key) != value for key, value in expected.items()):
        raise ValueError('Encoder runtime is not the configured pinned CPU MPNet contract')
    packages = runtime.get('packages', {})
    required = {'torch', 'sentence-transformers', 'transformers', 'numpy', 'tokenizers', 'safetensors', 'huggingface-hub'}
    if not isinstance(packages, dict) or not required <= set(packages) or any(
            config['package_versions'].get(name) != version for name, version in packages.items()):
        raise ValueError('Encoder runtime package provenance differs from the verified lock')
    vectors, matrix, norms = result.get('embeddings'), result.get('cosine_similarity'), result.get('norms')
    n = len(texts)
    def numeric(value):
        return type(value) in (int, float) and math.isfinite(value)
    if (not isinstance(vectors, list) or len(vectors) != n
            or any(not isinstance(row, list) or len(row) != 768 or not all(map(numeric, row)) for row in vectors)
            or not isinstance(matrix, list) or len(matrix) != n
            or any(not isinstance(row, list) or len(row) != n or not all(map(numeric, row)) for row in matrix)
            or not isinstance(norms, list) or len(norms) != n or not all(map(numeric, norms))):
        raise ValueError('Encoder vectors/matrix/norms have invalid shape or nonfinite values')
    for i, vector in enumerate(vectors):
        norm = math.sqrt(math.fsum(value * value for value in vector))
        if not math.isclose(norm, 1, abs_tol=1e-5) or not math.isclose(norms[i], norm, abs_tol=1e-5):
            raise ValueError('Encoder output vectors are not L2-normalized')
    # Cross-check the supplied matrix against its retained actual vectors.
    # Float32 BLAS output differs slightly from Python's float64 summation.
    for i, left in enumerate(vectors):
        for j, right in enumerate(vectors):
            if not math.isclose(matrix[i][j], math.fsum(a * b for a, b in zip(left, right)),
                                rel_tol=0, abs_tol=2e-5):
                raise ValueError('Encoder matrix differs from retained normalized embeddings')
    return result


def validate_encoder_request(request, extraction, evidence, config):
    """Replay provider binding from retained actual output, without re-encoding."""
    from oeq_sr_scoring import canonical_step_view
    if request.get('encoder_provider_sha256') != json_hash(config):
        raise ValueError('Encoder request does not match the selected provider configuration')
    generated = canonical_step_view(extraction, evidence['route_id'])
    reference = [row['text'] for row in evidence['sr_inventory']['reference_steps']]
    texts = reference + [row['text'] for row in generated]
    result = _validate_encoder_output(request.get('encoder_run'), texts, config)
    sliced = [row[len(reference):] for row in result['cosine_similarity'][:len(reference)]]
    if request.get('similarities') != sliced:
        raise ValueError('SR similarities differ from the actual reference-by-generated encoder slice')
    expected_encoder = {'id': config['model_id'], 'revision': config['revision'],
                        'input_representation': 'canonical_step_quote'}
    if (request.get('encoder') != expected_encoder or 'threshold' in request
            or request.get('matching_contract') != config.get('matching_contract')
            or config.get('schema_version') != 'local-pinned-mpnet-provider-continuous-v2'):
        raise ValueError('SR encoder identity or continuous matching contract changed')
    return request


async def build_pinned_step_request(extraction, evidence, config):
    from oeq_sr_scoring import canonical_step_view
    if evidence.get('route_id') is None or evidence.get('sr_inventory') is None:
        raise ValueError('Actual encoder requires one explicitly selected whole fixed reference')
    generated = canonical_step_view(extraction, evidence['route_id'])
    reference = evidence['sr_inventory']['reference_steps']
    texts = [row['text'] for row in reference] + [row['text'] for row in generated]
    result = await run_pinned_encoder(config, texts)
    request = {'canonical_extraction_sha256': json_hash(extraction),
               'task_evidence_sha256': json_hash(evidence), 'route_id': evidence['route_id'],
               'reference_id': evidence['reference_id'], 'generated_steps': generated,
               'reference_step_ids': [row['reference_step_id'] for row in reference],
               'reference_step_texts': [row['text'] for row in reference],
               'encoder': {'id': config['model_id'], 'revision': config['revision'],
                           'input_representation': 'canonical_step_quote'},
               'similarities': [row[len(reference):] for row in result.get('cosine_similarity', [])[:len(reference)]],
               'matching_contract': config['matching_contract'], 'encoder_provider_sha256': json_hash(config),
               'encoder_run': result}
    return validate_encoder_request(request, extraction, evidence, config)


def build_sr_context(question, protocol, task_evidence, study_context=None):
    """Use the task registry's frozen source/requirement snapshot everywhere."""
    study = deepcopy(study_context) if study_context is not None else {}
    if not isinstance(study, dict):
        raise ValueError('Task context must be an object')
    if study_context is not None and (study.get('question_sha256') != json_hash(question)
            or study.get('protocol_sha256') != text_hash(protocol)):
        raise ValueError('Explicit task context must bind this unchanged question and protocol')
    from oeq_task_evidence import validate_selected_task_evidence
    task_evidence = validate_selected_task_evidence(task_evidence)
    from oeq_target_responsibilities import formula_ids
    selected_ids = {r['id'] for r in task_evidence['requirements']}
    full_contract = bool(formula_ids(task_evidence['formula']) - selected_ids)
    fixed = {'cards': task_evidence['cards'],
             'requirements': task_evidence['fixed_requirements'] if full_contract else task_evidence['requirements'],
             'formula': task_evidence['formula']}
    for key in ('cards', 'requirements', 'formula'):
        if key in study and study[key] != fixed[key]:
            raise ValueError('Task context cannot replace fixed task evidence: ' + key)
        study[key] = deepcopy(fixed[key])
    if not study['requirements']:
        raise ValueError('Canonical SR assessment requires explicit nonempty fixed requirements; no defaults are invented')
    if study.get('extraction_mode', 'record_refs') != 'record_refs':
        raise ValueError('SR benchmark requires canonical record-reference extraction')
    target_checks = deepcopy(task_evidence['correctness_checks'])
    for metric, groups in task_evidence['submetrics'].items():
        if metric not in target_checks:
            continue
        for ids in groups.values():
            target_checks[metric].extend(rid for rid in ids if rid not in target_checks[metric])
    study['target_correctness_checks'] = target_checks
    study['target_selected_route'] = task_evidence['selected_route']
    study['extraction_mode'] = 'record_refs'
    study['question_sha256'] = json_hash(question)
    study['protocol_sha256'] = text_hash(protocol)
    return build_context(question, protocol, study_context=study)


def score_only_prompt(context, assessment, task_evidence):
    extraction = assessment['extraction']
    payload = {
        'question': context['question_meta'],
        'protocol_sha256': context['protocol_sha256'],
        'canonical_extraction_sha256': json_hash(extraction),
        'task_evidence_sha256': json_hash(task_evidence),
        'route_id': task_evidence.get('route_id'),
        'reference_id': task_evidence.get('reference_id'),
        'canonical_extraction': extraction,
        'extraction_fidelity': assessment['extraction_fidelity'],
        'method_identity': assessment['method_identity'],
        'fixed_task_evidence': task_evidence,
        'target_responsibilities': context['target_responsibilities'],
        'marker_input_contract': context.get('marker_input_contract'),
    }
    import json
    template = (ROOT / 'prompts/oeq_sr_score_only.txt').read_text(encoding='utf-8')
    return template + '\nSCORING_INPUT_JSON\n' + json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _duration_hours(value):
    """Only exact scalar durations; ranges/conditions/multipliers stay unknown."""
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(h|hrs?|hours?|min|minutes?|s|seconds?|d|days?|小时|分钟|秒|天)\s*', value, re.I)
    if not match:
        return None
    unit = match[2].casefold()
    factor = (24 if unit in {'d', 'day', 'days', '天'} else
              1/60 if unit in {'min', 'minute', 'minutes', '分钟'} else
              1/3600 if unit in {'s', 'second', 'seconds', '秒'} else 1)
    result = float(match[1]) * factor
    return result if math.isfinite(result) and result >= 0 else None


def _duration_scoring_value(value):
    """Explicit finite scalar or closed same-unit range; never impute missing time."""
    exact = _duration_hours(value)
    if exact is not None:
        unit = re.search(r'[^\d.\s].*', value).group().strip()
        return dict(bounds_h=[exact, exact], representative_hours=exact,
                    representative_kind='exact_scalar', source_unit=unit,
                    source_bounds=[float(re.match(r'\s*(\d+(?:\.\d+)?)', value)[1])] * 2)
    if not isinstance(value, str):
        return None
    number = r'(\d+(?:\.\d+)?)'
    unit = r'(h|hrs?|hours?|min|minutes?|s|seconds?|d|days?|小时|分钟|秒|天)'
    match = re.fullmatch(r'\s*' + number + r'\s*' + unit + r'?\s*(?:[-–—]|to|至|到)\s*' +
                         number + r'\s*' + unit + r'\s*', value, re.I)
    if not match:
        return None
    low, first_unit, high, last_unit = match.groups()
    low, high = float(low), float(high)
    if not all(math.isfinite(v) and v >= 0 for v in (low, high)) or low > high:
        return None
    factor = _duration_hours('1 ' + last_unit)
    if first_unit is not None and _duration_hours('1 ' + first_unit) != factor:
        return None
    bounds = [low * factor, high * factor]
    if not all(math.isfinite(v) for v in bounds):
        return None
    return dict(bounds_h=bounds, representative_hours=bounds[0] / 2 + bounds[1] / 2,
                representative_kind='range_midpoint', source_unit=last_unit,
                source_endpoint_units=[first_unit, last_unit], source_bounds=[low, high])


def _scoped_time_relation_spans(protocol, left, right, facts, selected_route):
    """Bound new relation guards to time records or explicit open controls.

    This is a conservative finite grammar, not general control-flow inference.
    Existing repeat/concurrency guards are intentionally separate and unchanged.
    """
    cue = re.compile(r'\b(?:every|either|or|if|unless|optionally|until)\b'
                     r'|每隔|每(?=\s*\d|天|日|周|月|小时|分钟)|或(?:者)?|如果|除非|直到|(?:^\s*|[，,:：;；]\s*)若(?!干)', re.I)
    witnesses, bound_headings = [], []
    for (collection, _), fact in facts.items():
        if collection != 'steps' or fact.get('branch') != selected_route:
            continue
        witnesses.extend(fact.get('fields', {}).get('duration_text', {}).get('spans', []))
        assertion = fact.get('assertion', {})
        if isinstance(assertion.get('heading_span'), dict):
            bound_headings.append(assertion['heading_span'])
        phase_binding = fact.get('fields', {}).get('phase', {}).get('scope_binding') or {}
        if isinstance(phase_binding.get('heading'), dict):
            bound_headings.append(phase_binding['heading'])
    def valid(span):
        return (type(span.get('start')) is int and type(span.get('end')) is int
                and left <= span['start'] < span['end'] <= right)
    witnesses = [span for span in witnesses if valid(span)]
    scopes = [(span['start'], span['end'], 'BOUND_STEP_HEADING')
              for span in bound_headings if valid(span)]
    # Sentence/line boundaries keep independent documentation clauses out of a
    # time record, without splitting decimal numbers in the time itself.
    start = left
    for boundary in re.finditer(r'[.!?。！？](?=\s|$)|[\r\n]', protocol[left:right]):
        end = left + boundary.end()
        if any(start <= span['start'] < span['end'] <= end for span in witnesses):
            scopes.append((start, end, 'DURATION_WITNESS_SENTENCE'))
        start = end
    if any(start <= span['start'] < span['end'] <= right for span in witnesses):
        scopes.append((start, right, 'DURATION_WITNESS_SENTENCE'))
    offset = left
    for line in protocol[left:right].splitlines(keepends=True):
        end = offset + len(line)
        body = re.sub(r'^\s*(?:[-*#]+|\d+(?:\.\d+)*[.)]?)?\s*', '', line).strip()
        # Only control lines before a time-bearing record can scope later work.
        # A complete comma-separated conditional with an independent main clause
        # is not an open control unless it explicitly introduces following work.
        later = any(span['start'] >= end for span in witnesses)
        conditional = re.match(r'^(?:if|unless)\b|^(?:如果|除非|若(?!干))', body, re.I)
        explicit_block = body.rstrip().endswith((':', '：'))
        forward_reference = re.search(r'\b(?:following|below)\b|以下|下列', body, re.I)
        task_reference = re.search(r'\b(?:steps?|tasks?)\b|步骤|任务', body, re.I)
        dangling_condition = re.fullmatch(r'(?:if|unless)\s+[A-Za-z]+ed[.!]?|(?:如果|若).+[：:]', body, re.I)
        schedule_directive = re.match(r'^(?:(?:run|execute|perform)\s+)?every\b|^wait\s+until\b', body, re.I)
        if later and cue.search(body) and (explicit_block or forward_reference
                or (task_reference and re.match(r'^(?:if|unless|choose|run|execute|perform|every)\b', body, re.I))
                or dangling_condition or schedule_directive):
            scopes.append((offset, end, 'EXPLICIT_OPEN_CONTROL_BEFORE_TIME_RECORD'))
        offset = end
    found = {}
    for start, end, basis in scopes:
        for match in cue.finditer(protocol[start:end]):
            a, b = start + match.start(), start + match.end()
            found[(a,b,basis)] = dict(start=a,end=b,quote=protocol[a:b],scope_basis=basis,
                scope_span=dict(start=start,end=end,quote=protocol[start:end]))
    return list(found.values())


def project_effectiveness_inputs(assessment, selected_route, question_metadata, *, protocol=None):
    """Conservative deterministic bridge to existing E formula inputs.

    No second extraction, generic method recipes, source borrowing, alternative mixing, or implicit fluorophore inference occurs.
    Explicit finite ranges retain their bounds and supply a midpoint scoring
    representative. Only affirmed clearing-phase nodes on one serial route sum.
    """
    extraction = assessment['extraction']
    branches = {row['id']: row for row in extraction['branches']}
    branch = branches.get(selected_route)
    facts = {(row['collection'], row['index']): row
             for row in assessment['extraction_fidelity']['facts']}
    guards = {'method': [], 'labels': [], 'time': []}

    def eligible(collection, index, fields):
        fact = facts.get((collection, index), {})
        return (fact.get('branch') == selected_route and
                fact.get('assertion', {}).get('polarity') == 'AFFIRMED' and
                not (collection == 'steps' and fact.get('assertion', {}).get('scope') == 'MAIN_DIRECTIVE') and
                all(fact.get('fields', {}).get(field, {}).get('status') == 'GROUNDED'
                    for field in fields))

    method = None
    route_identity = _route_method_identity(assessment['method_identity'], selected_route, extraction)
    names = route_identity['selected_methods']
    if branch is not None and route_identity['status'] == 'SATISFIED' and len(names) == 1 and names[0]:
        method = names[0]
    else:
        guards['method'].append('SELECTED_ROUTE_METHOD_UNRESOLVED')

    markers, label_ids = {}, []
    selected_labels = [(i, row) for i, row in enumerate(extraction['labels']) if row['branch'] == selected_route]
    if not selected_labels:
        guards['labels'].append('NO_EXPLICIT_SELECTED_ROUTE_LABELS')
    for index, row in selected_labels:
        # The probe/fluorophore relation must come from this very label record.
        if not eligible('labels', index, ('probe', 'fluorophore')) or not row['probe'] or not row['fluorophore']:
            guards['labels'].append('LABEL_RELATION_UNRESOLVED:' + row['id'])
            continue
        fluor, probe = row['fluorophore'], row['probe']
        if fluor in markers and markers[fluor] != probe:
            guards['labels'].append('MULTIPLE_PROBES_FOR_FLUOROPHORE:' + fluor)
        markers[fluor] = probe
        label_ids.append(row['id'])

    times, time_ids, duration_values = [], [], []
    selected_steps = [(i, row) for i, row in enumerate(extraction['steps']) if row['branch'] == selected_route]
    if branch is None or branch.get('mode') != 'SERIAL' or branch.get('location_status') == 'REVIEW_REQUIRED':
        guards['time'].append('SELECTED_SERIAL_ROUTE_UNRESOLVED')
    for index, row in selected_steps:
        phase = re.sub(r'^[\s#*\d.()、]+|[\s:*：]+$', '', row.get('phase') or '').casefold()
        if phase in {'clearing', 'processing', '透明', '光透明', '透明处理'}:
            duration = _duration_scoring_value(row.get('duration_text'))
            if duration is None or not eligible('steps', index, ('phase', 'operation', 'duration_text')):
                guards['time'].append('CLEARING_DURATION_UNRESOLVED:' + row['id'])
            else:
                source_spans = deepcopy(facts[('steps', index)]['fields']['duration_text'].get('spans', []))
                # Newly accepted ranges must retain a verifiable source witness.
                if duration['representative_kind'] == 'range_midpoint' and not (
                        isinstance(protocol, str) and any(
                            type(span.get('start')) is int and type(span.get('end')) is int
                            and 0 <= span['start'] < span['end'] <= len(protocol)
                            and row['duration_text'].strip() in protocol[span['start']:span['end']]
                            for span in source_spans)):
                    guards['time'].append('RANGE_SOURCE_SPAN_UNRESOLVED:' + row['id'])
                    continue
                for span in source_spans:
                    if isinstance(protocol, str) and type(span.get('start')) is int and type(span.get('end')) is int:
                        span['quote'] = protocol[span['start']:span['end']]
                duration_values.append(dict(step_id=row['id'], source_text=row['duration_text'],
                                            source_spans=source_spans, **duration))
                times.append(duration['representative_hours'])
                time_ids.append(row['id'])
        elif phase not in {'labeling', 'labelling', 'label preparation', 'storage', 'imaging',
                            'pretreatment', 'pre-treatment', 'postprocessing', 'post-processing',
                            '前处理', '预处理', '后处理', '终处理', '标记准备', '标签准备', '保存', '存储', '成像'}:
            guards['time'].append('STEP_PHASE_UNRESOLVED:' + row['id'])
    if not times:
        guards['time'].append('NO_EXPLICIT_CLEARING_DURATIONS')
    reference_audit = assessment.get('extraction_reference_audit') or {}
    if reference_audit.get('coverage', {}).get('omitted_record_ids'):
        guards['time'].append('CANONICAL_RECORD_COVERAGE_INCOMPLETE')
    time_scope_audit = {'protocol_sha256': text_hash(protocol) if isinstance(protocol, str) else None,
                        'unrepresented_duration_spans': [], 'unhandled_relation_spans': []}
    if not isinstance(protocol, str):
        guards['time'].append('UNCHANGED_PROTOCOL_REQUIRED_FOR_TIME_SCOPE')
    elif text_hash(protocol) != extraction.get('field_audit', {}).get('protocol_sha256'):
        raise ValueError('Time projection protocol differs from canonical extraction source')
    else:
        regions = (branch or {}).get('resolved_spans') or (branch or {}).get('spans') or []
        if branch and not regions and branch['id'] == 'main' and len(branches) == 1:
            regions = [{'start': 0, 'end': len(protocol)}]
        if not regions:
            guards['time'].append('SELECTED_ROUTE_TIME_LOCATION_UNRESOLVED')
        spans = [span for (collection, index), fact in facts.items()
                 if collection == 'steps' and fact.get('branch') == selected_route
                 for span in fact.get('fields', {}).get('duration_text', {}).get('spans', [])]
        duration_pattern = (r'(?<![\w.])\d+(?:\.\d+)?\s*(?:hours?|h|minutes?|min|seconds?|s|days?|d)\b'
                            r'|\d+(?:\.\d+)?\s*(?:小时|分钟|秒|天)|\bovernight\b|过夜')
        relation_pattern = (r'\b(?:repeat(?:ed|ing)?|repetitions?|iterations?|rounds?|twice|thrice|cycles?|times|each|parallel|concurrent(?:ly)?|'
                            r'simultaneous(?:ly)?|meanwhile|overlap(?:ping)?|while|during)\b'
                            r'|(?:[×x]\s*\d+|\d+\s*[×x](?![a-z])|\d+\s*[次轮遍])|重复|循环|轮次|每次|同时|并行|并发|同步')
        for region in regions:
            if (type(region.get('start')) is not int or type(region.get('end')) is not int
                    or not 0 <= region['start'] < region['end'] <= len(protocol)):
                guards['time'].append('SELECTED_ROUTE_TIME_LOCATION_UNRESOLVED')
                continue
            left, right = region['start'], region['end']
            body = protocol[left:right]
            for match in re.finditer(duration_pattern, body, re.I):
                start, end = left + match.start(), left + match.end()
                if not any(span['start'] <= start < end <= span['end'] for span in spans):
                    time_scope_audit['unrepresented_duration_spans'].append(
                        {'start': start, 'end': end, 'quote': protocol[start:end]})
            for match in re.finditer(relation_pattern, body, re.I):
                start, end = left + match.start(), left + match.end()
                time_scope_audit['unhandled_relation_spans'].append(
                    {'start': start, 'end': end, 'quote': protocol[start:end],
                     'scope_basis': 'EXISTING_ROUTE_WIDE_REPEAT_CONCURRENCY_GUARD'})
            time_scope_audit['unhandled_relation_spans'].extend(
                _scoped_time_relation_spans(protocol, left, right, facts, selected_route))
        for value in duration_values:
            if value['representative_kind'] == 'range_midpoint' and not any(
                    type(region.get('start')) is int and type(region.get('end')) is int
                    and region['start'] <= span['start'] < span['end'] <= region['end']
                    for region in regions for span in value['source_spans']):
                guards['time'].append('RANGE_SOURCE_OUTSIDE_SELECTED_ROUTE:' + value['step_id'])
        if time_scope_audit['unrepresented_duration_spans']:
            guards['time'].append('DURATION_OUTSIDE_CANONICAL_STEP_FIELDS')
        if time_scope_audit['unhandled_relation_spans']:
            guards['time'].append('REPEAT_CONCURRENCY_OR_TIME_RELATION_UNRESOLVED')
    total_bounds = None
    total_hours = None
    if not guards['time']:
        try:
            total_bounds = [math.fsum(v['bounds_h'][k] for v in duration_values) for k in (0, 1)]
            total_hours = math.fsum(times)
            if not all(math.isfinite(v) for v in [*total_bounds, total_hours]):
                raise OverflowError('Non-finite total duration')
        except OverflowError:
            guards['time'].append('NONFINITE_TOTAL_DURATION')
            total_bounds, total_hours = None, None
    quantitative = {
        'method_name': method,
        'tissue_ri_value': question_metadata.get('tissue_ri_value'),
        'tissue_ri_reference': deepcopy(question_metadata.get('tissue_ri_reference')),
        'sample_tier': question_metadata.get('tissue_tier_code'),
        'total_time_hours': total_hours,
    }
    return {
        'schema_version': 'canonical-effectiveness-projection-v3-range-midpoint',
        'sample_ri_reference_policy': ri_reference_policy(),
        'canonical_extraction_sha256': json_hash(extraction),
        'selected_route': selected_route, 'quantitative_data': quantitative,
        'marker_dict': markers if not guards['labels'] else {},
        'marker_query_targets': deepcopy(question_metadata.get('marker_query_targets') or []),
        'source_ids': {'label_ids': label_ids, 'duration_step_ids': time_ids},
        'guards': guards, 'branches': deepcopy(extraction['branches']),
        'route_method_identity': route_identity, 'time_scope_audit': time_scope_audit,
        'time_policy': 'explicit_scalar_or_range_midpoint_affirmed_clearing_phase_selected_serial_route',
        'time_representation': {
            'duration_values': duration_values, 'total_bounds_h': total_bounds,
            'scoring_representative_hours': total_hours,
            'representative_kind': (None if total_hours is None else
                'range_midpoint' if any(v['representative_kind'] == 'range_midpoint' for v in duration_values)
                else 'exact_scalar'),
            'scope': 'SELECTED_SERIAL_CLEARING_PHASE_ONLY',
        },
    }


def effectiveness_from_canonical(assessment, task_evidence, question_metadata,
                                 user_preference_vector, model_space, effectiveness_fn, *, protocol):
    projection = project_effectiveness_inputs(assessment, task_evidence.get('route_id'), question_metadata, protocol=protocol)
    raw = effectiveness_fn(projection['quantitative_data'], user_preference_vector, model_space,
                           projection['marker_dict'], projection['marker_query_targets'])
    maxima = {'s_method': 2.5, 's_label': 6, 's_trans': 3, 's_time': 3}
    scores = {}
    for key, maximum in maxima.items():
        value = raw[key]
        scores[key] = {'score': value, 'max_score': maximum,
                       'reasoning': 'Unchanged deterministic E function on the canonical route projection.'}
        if value is None:
            scores[key]['missing_reason'] = 'Canonical projection or existing KB inputs unresolved'
    inputs = {'canonical_extraction_sha256': json_hash(assessment['extraction']),
              'selected_route': task_evidence.get('route_id'), 'projection': projection,
              'question_metadata': deepcopy(question_metadata),
              'user_preference_vector': deepcopy(user_preference_vector),
              'model_space_sha256': json_hash(model_space), 'calculation_diagnostics': raw}
    return scores, inputs


def _assemble(entry, context, task_evidence, step_request, generations,
              question_metadata, user_preference_vector, model_space, effectiveness_fn,
              canonical_raw=None, assessment=None, encoder_config=None):
    from oeq_sr_scoring import build_sr_benchmark_record
    from experiments.construct_validity.answer_matching import status_summary
    canonical_raw = (parse_judge_object(generations['canonical']['content'])
                     if canonical_raw is None else canonical_raw)
    assessment = (apply_assessment(canonical_raw, context, entry['model_response'])
                  if assessment is None else assessment)
    if encoder_config is not None:
        validate_encoder_request(step_request, assessment['extraction'], task_evidence, encoder_config)
    prompt = score_only_prompt(context, assessment, task_evidence)
    score_raw = parse_judge_object(generations['score_only']['content'])
    effectiveness, inputs = effectiveness_from_canonical(
        assessment, task_evidence, question_metadata, user_preference_vector, model_space, effectiveness_fn,
        protocol=entry['model_response'])
    result = build_sr_benchmark_record(
        protocol=entry['model_response'], canonical_extraction=assessment['extraction'],
        task_evidence=task_evidence, score_proposal=score_raw, step_request=step_request,
        effectiveness_scores=effectiveness, effectiveness_input=inputs,
        raw_generations=deepcopy(generations), record_id=str(entry['question_id']))
    result['sr_assessment'] = {
        'schema_version': VERSION, 'canonical_assessment': assessment,
        'target_responsibilities': deepcopy(context['target_responsibilities']),
        **status_summary(assessment['answer_matching']),
        'scientific_status_interpretation': 'SR_TOP_LEVEL_UNRESOLVED_IS_NOT_CANONICAL_CLAIM_AGGREGATE',
        'encoder_config': deepcopy(encoder_config),
        'canonical_assessment_sha256': json_hash(assessment),
        'canonical_proposal': canonical_raw, 'score_proposal': score_raw,
        'output_schema_sha256': {name: json_hash(output_schema(name)) for name in ('canonical', 'score_only')},
        'canonical_prompt_sha256': context['prompt_sha256'],
        'score_prompt_sha256': text_hash(prompt), 'context_sha256': context['context_sha256'],
        'raw_generations': deepcopy(generations), 'raw_generations_sha256': json_hash(generations),
    }
    return result


async def evaluate_sr_response(teacher_model, entry, context, task_evidence, step_request, *,
                               get_response, effectiveness_fn, question_metadata,
                               user_preference_vector, model_space, recorded_generations=None, encoder_config=None):
    """Two stages, one extraction; explicit recorded generations are offline data."""
    result = {'technical_status': 'FAILED', 'assessment_mode': 'sr-benchmark',
              'sr_assessment_version': VERSION, 'cce_eligible': False, 'official_scores': None,
              'raw_generations': {}, 'context_sha256': context['context_sha256']}
    stage = 'CANONICAL_GENERATION'
    try:
        generations = result['raw_generations']
        async def generate(name, prompt):
            if recorded_generations is not None:
                if name not in recorded_generations:
                    raise ValueError('Recorded fixture lacks ' + name)
                record = deepcopy(recorded_generations[name])
            else:
                record = await get_response(_stage_model(teacher_model, name), prompt, return_data=True, validate_protocol=False)
            generations[name] = record
            if record.get('technical_status') != 'VALID':
                raise ValueError(name + ' generation failed: ' + str(record.get('failure_code')))
            return parse_judge_object(record['content'])
        canonical_raw = await generate('canonical', context['prompt'])
        result['canonical_proposal'] = deepcopy(canonical_raw)
        stage = 'CANONICAL_VALIDATION'
        assessment = apply_assessment(canonical_raw, context, entry['model_response'])
        result['canonical_assessment'] = assessment
        if encoder_config is not None:
            stage = 'STEP_ENCODER'
            step_request = await build_pinned_step_request(assessment['extraction'], task_evidence, encoder_config)
            result['step_request'] = deepcopy(step_request)
        stage = 'STEP_INPUT_VALIDATION'
        from oeq_sr_scoring import validate_step_request
        validate_step_request(step_request, assessment['extraction'], task_evidence)
        stage = 'SCORE_ONLY_GENERATION'
        await generate('score_only', score_only_prompt(context, assessment, task_evidence))
        stage = 'SR_RECORD_VALIDATION'
        return _assemble(entry, context, task_evidence, step_request, generations,
                         question_metadata, user_preference_vector, model_space, effectiveness_fn,
                         canonical_raw=canonical_raw, assessment=assessment, encoder_config=encoder_config)
    except (ValueError, TypeError, KeyError, StopIteration, OSError, asyncio.TimeoutError) as exc:
        result.update(_error=str(exc), _error_type=type(exc).__name__, failure_stage=stage)
        return result


def sr_assessment_complete(evaluation, *, entry=None, context=None, task_evidence=None,
                           step_request=None, question_metadata=None, user_preference_vector=None,
                           model_space=None, effectiveness_fn=None, encoder_config=None):
    """Resume validates raw proposals and deterministically replays every stage."""
    from oeq_sr_scoring import is_sr_benchmark_record_complete
    if not is_sr_benchmark_record_complete(evaluation, protocol=entry['model_response'] if entry else None):
        return False
    bridge = evaluation.get('sr_assessment', {})
    if bridge.get('schema_version') != VERSION:
        return False
    from oeq_scientific import VERSION as SCIENTIFIC_VERSION
    from experiments.construct_validity.answer_matching import validated_assessment_status_summary
    canonical = bridge.get('canonical_assessment', {})
    try:
        summary = validated_assessment_status_summary(canonical)
        if (canonical.get('schema_version') != SCIENTIFIC_VERSION
                or bridge.get('target_responsibilities') != canonical.get('target_responsibilities')
                or not isinstance(canonical.get('target_responsibilities'), dict)
                or any(bridge.get(k) != v for k, v in summary.items())):
            return False
    except (ValueError, KeyError, TypeError):
        return False
    generations = bridge.get('raw_generations')
    if (not isinstance(generations, dict) or bridge.get('raw_generations_sha256') != json_hash(generations)
            or any(generations.get(k, {}).get('technical_status') != 'VALID' for k in ('canonical', 'score_only'))):
        return False
    try:
        if (parse_judge_object(generations['canonical']['content']) != bridge.get('canonical_proposal')
                or parse_judge_object(generations['score_only']['content']) != bridge.get('score_proposal')
                or generations != evaluation.get('raw_generations')
                or bridge.get('score_proposal') != evaluation.get('score_proposal')
                or bridge.get('canonical_assessment', {}).get('extraction') != evaluation.get('canonical_extraction')):
            return False
    except (ValueError, TypeError, KeyError):
        return False
    if context is None:
        try:
            if bridge.get('encoder_config') is not None:
                validate_encoder_request(evaluation['step_request'], evaluation['canonical_extraction'],
                                         evaluation['task_evidence'], bridge['encoder_config'])
            return bridge.get('canonical_assessment_sha256') == json_hash(bridge.get('canonical_assessment'))
        except (ValueError, TypeError, KeyError):
            return False
    try:
        if encoder_config is not None:
            step_request = evaluation.get('step_request')
        rebuilt = _assemble(entry, context, task_evidence, step_request, generations,
                            question_metadata, user_preference_vector, model_space, effectiveness_fn,
                            encoder_config=encoder_config)
        return rebuilt == evaluation
    except (ValueError, TypeError, KeyError, StopIteration):
        return False
