"""Prepare, run, and analyze a frozen repeat-grading / human-blind-review pilot.

Standard library only. Run from the repository root; `prepare` and `analyze`
are offline. `run` explicitly uses a configured model API and may incur charges.
"""
import argparse
import asyncio
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import io
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation_contract import FixedDemandRegistry, ensure_manifest, json_hash, sha256_file
from results.oeq_metrics import protocol_scores

STUDY_VERSION = 'repeat-grading-blind-pilot-v1'
QUESTION_FILE = ROOT / 'dataset/Q+AR/revisions/2026-09-13-stem-fixes/before/question_final.json'
DEMAND_FILE = ROOT / 'dataset/Q+AR/src/demand_vectors_all.json'
MODELS = ['openai_gpt-5.2-fast', 'openai_qwen3-max', 'openai_qwen3-14b']
SETTINGS = ['1-shot', '1-shot+KB-RAG', '1-shot+KB-RAG+self-check']
RATING_FIELDS = [
    {'key': 'overall_feasibility', 'label': '总体：按方案实现本题目标的可行性',
     'hint': '请做独立的总体判断，不按下面子项机械求平均。',
     'options': [['0', '0 — 存在根本性问题，无法实现目标'], ['1', '1 — 需要重大修改'],
                 ['2', '2 — 需要若干实质修正'], ['3', '3 — 少量补充或澄清后可用'],
                 ['4', '4 — 未发现妨碍实现目标的问题'], ['U', '无法判断']]},
    {'key': 'target_coverage', 'label': '必需观察目标是否覆盖', 'hint': '按本题要求逐项检查，区分必需目标和辅助通道。',
     'options': [['0', '0 — 关键目标未覆盖'], ['1', '1 — 仅少部分覆盖'], ['2', '2 — 大部分覆盖'], ['3', '3 — 必需目标均覆盖'], ['U', '无法判断']]},
    {'key': 'label_method_compatibility', 'label': '标记与透明方法的兼容性', 'hint': '考虑具体样本、荧光团、条件和必要前处理。',
     'options': [['0', '0 — 存在明确致命冲突'], ['1', '1 — 存在重要未解决冲突'], ['2', '2 — 有条件可行，需补充说明'], ['3', '3 — 未发现重要兼容性问题'], ['U', '无法判断']]},
    {'key': 'physical_validity', 'label': '步骤、试剂与参数的科学合理性', 'hint': '指出实际物理、化学或方法学冲突。',
     'options': [['0', '0 — 根本不可行'], ['1', '1 — 存在重大错误'], ['2', '2 — 有局部问题'], ['3', '3 — 未发现重要问题'], ['U', '无法判断']]},
    {'key': 'execution_completeness', 'label': '题目要求范围内的执行信息完整性', 'hint': '不对题目明确排除或已完成的步骤重复扣分。',
     'options': [['0', '0 — 缺少关键内容'], ['1', '1 — 缺项较多'], ['2', '2 — 基本完整'], ['3', '3 — 足够明确完整'], ['U', '无法判断']]},
    {'key': 'fatal_issue', 'label': '是否存在阻止目标实现的致命问题', 'hint': '选择“是”时，请在判断依据中指出问题。',
     'options': [['no', '未发现'], ['yes', '是'], ['uncertain', '不确定']]},
    {'key': 'confidence', 'label': '对此次判断的把握', 'hint': '反映证据和个人专业覆盖程度。',
     'options': [['1', '较低'], ['2', '中等'], ['3', '较高']]},
]
TEXT_FIELDS = ['rationale', 'references', 'unable_reason']


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temporary.replace(path)


def write_frozen(path, text):
    path = Path(path)
    encoded = text.encode('utf-8')
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError(f'Existing study material differs: {path}. Use another study directory.')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)


def frozen_json(path, data):
    write_frozen(path, json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def csv_text(rows, fields):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def index_unique(items, key):
    indexed = {str(item[key]): item for item in items}
    if len(indexed) != len(items):
        raise ValueError(f'Duplicate {key}')
    return indexed


def prepare(study_dir, seed=20260921):
    """One scenario per each of the 12 tissue strata; balanced model assignment.

    Select by metadata/available answer text, before reading historical scores.
    Each selected (question, model) contributes all three conditions.
    """
    study_dir = Path(study_dir).resolve()
    rng = random.Random(seed)
    questions = read_json(QUESTION_FILE)
    FixedDemandRegistry(QUESTION_FILE, DEMAND_FILE)
    question_map = index_unique(questions, 'question_id')
    source_hashes = {str(QUESTION_FILE.relative_to(ROOT)): sha256_file(QUESTION_FILE),
                     str(DEMAND_FILE.relative_to(ROOT)): sha256_file(DEMAND_FILE)}
    responses = {}
    for model in MODELS:
        for setting in SETTINGS:
            path = ROOT / f'dataset/Q+AR/model_response/from_{model}_{setting}.json'
            source_hashes[str(path.relative_to(ROOT))] = sha256_file(path)
            responses[model, setting] = index_unique(read_json(path), 'question_id')
    strata = defaultdict(list)
    for question in questions:
        strata[question['tissue_hierarchy_from_tissue_xlsx']['tissue_tier_code']].append(question['question_id'])
    if len(strata) != 12:
        raise ValueError('This pilot specifies 12 tissue strata; revise the design explicitly for another dataset.')
    assigned_models = MODELS * 4
    rng.shuffle(assigned_models)
    selections, items = [], []
    for tier, model in zip(sorted(strata), assigned_models):
        eligible = [qid for qid in sorted(strata[tier]) if all(
            responses[model, setting].get(str(qid), {}).get('model_response', '').strip() for setting in SETTINGS)]
        if not eligible:
            raise ValueError(f'No available three-condition response set in {tier}/{model}')
        qid = rng.choice(eligible)
        question = question_map[str(qid)]
        selections.append({'question_id': qid, 'tissue_tier': tier, 'model': model, 'eligible_n': len(eligible)})
        for setting in SETTINGS:
            response = responses[model, setting][str(qid)]
            if response['specific_question'] != question['question']:
                raise ValueError(f'Response/question version mismatch: {model}/{setting}/{qid}')
            items.append({'item_id': f'P{len(items) + 1:03}', 'question_id': qid, 'tissue_tier': tier,
                          'model': model, 'setting': setting, 'question': question['question'],
                          'protocol': response['model_response'], 'restrictions': response.get('restrictions', ''),
                          'protocol_sha256': json_hash(response['model_response']),
                          'source_response_sha256': json_hash(response)})
    # Read scores only after the sample is frozen. Judge failures do not exclude answers.
    score_tables = {}
    for model in MODELS:
        for setting in SETTINGS:
            path = ROOT / f'dataset/Q+AR/result/evaluation_results_{model}_{setting}.json'
            source_hashes[str(path.relative_to(ROOT))] = sha256_file(path)
            score_tables[model, setting] = index_unique(read_json(path), 'question_id')
    for item in items:
        record = score_tables[item['model'], item['setting']].get(str(item['question_id']), {})
        try:
            score = protocol_scores(record)
            item['archived_indices'] = {key: score[key] for key in ('Com', 'Cor', 'Eff', 'I_A')}
        except ValueError:
            item['archived_indices'] = None
    plan = {
        'study_version': STUDY_VERSION, 'sampling_seed': seed,
        'question_file': str(QUESTION_FILE.relative_to(ROOT)), 'source_sha256': source_hashes,
        'selection': selections, 'n_scenarios': 12, 'n_protocols': 36, 'planned_repeats': 3,
        'planned_judge_calls': 108, 'planned_reviewers': ['A', 'B'],
        'reviewer_unique_protocols': 36, 'reviewer_hidden_repeat_items': 4,
        'selection_rule': 'One random question per tissue tier; model assignment balanced (4 scenarios/model); no selection on score or condition difference.',
        'inferential_unit': 'question-model scenario (12 clusters), not 108 independent judge calls',
        'scope': 'Exploratory pilot conditional on frozen archived answers; equal tissue-stratum weights; not a 253-question population estimate or a causal self-check trial.',
    }
    package_id = json_hash(plan)[:16]
    plan['package_id'] = package_id
    frozen_json(study_dir / 'private/study_manifest.json', plan)
    frozen_json(study_dir / 'private/items.json', items)
    assignments = []
    template = (ROOT / 'experiments/blind_review_template.html').read_text(encoding='utf-8')
    duplicated = rng.sample([item['item_id'] for item in items], 4)
    by_id = {item['item_id']: item for item in items}
    for reviewer in ('A', 'B'):
        order = [item['item_id'] for item in items] + duplicated
        for _ in range(1000):
            rng.shuffle(order)
            if all(abs(order.index(item_id) - (len(order) - 1 - order[::-1].index(item_id))) >= 10 for item_id in duplicated):
                break
        else:
            raise ValueError('Could not construct separated duplicate presentations')
        cases, ratings, seen = [], [], set()
        for position, item_id in enumerate(order):
            item = by_id[item_id]
            blind_id = reviewer + '-' + f'{rng.getrandbits(48):012X}'
            assignments.append({'reviewer_id': reviewer, 'blind_id': blind_id, 'position': position + 1,
                                'item_id': item_id, 'is_repeat': item_id in seen})
            seen.add(item_id)
            cases.append({'blind_id': blind_id, 'question': item['question'], 'protocol': item['protocol'],
                          'restrictions': item['restrictions']})
            ratings.append({'package_id': package_id, 'reviewer_id': reviewer, 'blind_id': blind_id,
                            **{key: '' for key in [*(field['key'] for field in RATING_FIELDS), *TEXT_FIELDS, 'recorded_at']}})
        review_data = {'package_id': package_id, 'reviewer_id': reviewer, 'rating_fields': RATING_FIELDS, 'cases': cases}
        embedded = json.dumps(review_data, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
        write_frozen(study_dir / f'reviewer_{reviewer}/index.html', template.replace('__REVIEW_DATA__', embedded))
        write_frozen(study_dir / f'reviewer_{reviewer}/ratings_template.csv', csv_text(ratings, list(ratings[0])))
        frozen_json(study_dir / f'reviewer_{reviewer}/cases.json', review_data)
    frozen_json(study_dir / 'private/blinding_key.json', assignments)
    archive = read_json(ROOT / 'dataset/Q+AR/result/Machine_vs_Human_Summary.json')
    frozen_json(study_dir / 'private/human_archive_provenance.json', {
        'source': 'dataset/Q+AR/result/Machine_vs_Human_Summary.json', 'records': len(archive),
        'source_sha256': sha256_file(ROOT / 'dataset/Q+AR/result/Machine_vs_Human_Summary.json'),
        'missing_grader_name': sum(not row.get('human_evaluation', {}).get('grader_name') for row in archive),
        'missing_grading_time': sum(not row.get('human_evaluation', {}).get('grading_time') for row in archive),
        'interpretation': 'Historical table only. Missing metadata does not establish who rated it or whether it was blinded; not reused as newly collected expert ratings.',
    })
    frozen_json(study_dir / 'private/call_schedule.json', make_schedule(items, seed, repeats=3))
    print(json.dumps({'package_id': package_id, 'scenarios': len(selections), 'protocols': len(items),
                      'planned_calls': 108, 'reviewer_presentations_each': 40, 'output': str(study_dir)}, ensure_ascii=False))
    return plan


def make_schedule(items, seed, repeats):
    rng = random.Random(seed + 73)
    tasks = []
    for repeat in range(1, repeats + 1):
        ids = [item['item_id'] for item in items]
        rng.shuffle(ids)
        tasks.extend({'repeat': repeat, 'item_id': item_id} for item_id in ids)
    return tasks


def load_validated_study(study_dir):
    """Recheck frozen inputs against their original files before spending on calls."""
    study_dir = Path(study_dir)
    plan = read_json(study_dir / 'private/study_manifest.json')
    if plan.get('package_id') != json_hash({k: v for k, v in plan.items() if k != 'package_id'})[:16]:
        raise ValueError('Study manifest/package hash mismatch')
    for relative, digest in plan['source_sha256'].items():
        source = (ROOT / relative).resolve()
        if not source.is_relative_to(ROOT) or sha256_file(source) != digest:
            raise ValueError(f'Frozen source changed: {relative}')
    items = read_json(study_dir / 'private/items.json')
    by_id = index_unique(items, 'item_id')
    expected = {(str(s['question_id']), s['model'], setting)
                for s in plan['selection'] for setting in SETTINGS}
    actual = {(str(i['question_id']), i['model'], i['setting']) for i in items}
    if len(items) != plan['n_protocols'] or actual != expected or len(actual) != len(items):
        raise ValueError('Frozen protocol set does not match the sampling plan')
    registry = FixedDemandRegistry(ROOT / plan['question_file'], DEMAND_FILE)
    sources = {}
    for item in items:
        registry.get(item['question_id'], item['question'])
        key = (item['model'], item['setting'])
        if key not in sources:
            path = ROOT / f'dataset/Q+AR/model_response/from_{key[0]}_{key[1]}.json'
            sources[key] = index_unique(read_json(path), 'question_id')
        original = sources[key][str(item['question_id'])]
        if (json_hash(item['protocol']) != item['protocol_sha256'] or
                item['protocol'] != original['model_response'] or
                item['question'] != original['specific_question'] or
                item['restrictions'] != original.get('restrictions', '') or
                item['source_response_sha256'] != json_hash(original)):
            raise ValueError(f'Frozen protocol changed: {item["item_id"]}')
    schedule = read_json(study_dir / 'private/call_schedule.json')
    if (schedule != make_schedule(items, plan['sampling_seed'], plan['planned_repeats']) or
            len(schedule) != plan['planned_judge_calls']):
        raise ValueError('Frozen call schedule changed')
    return plan, by_id, schedule


def validate_attempt(row, path, run_dir, by_id, schedule, contract_hash):
    if row.get('run_contract_sha256') != contract_hash:
        raise ValueError(f'Judge attempt contract mismatch: {path}')
    task = {'item_id': row.get('item_id'), 'repeat': row.get('repeat')}
    if task not in schedule or isinstance(task['repeat'], bool):
        raise ValueError(f'Unplanned judge attempt: {path}')
    expected_path = Path(run_dir) / f"repeat_{task['repeat']:02d}/{task['item_id']}.json"
    if Path(path).resolve() != expected_path.resolve():
        raise ValueError(f'Judge attempt path/identity mismatch: {path}')
    item = by_id[task['item_id']]
    if row.get('protocol_sha256') != item['protocol_sha256']:
        raise ValueError('Protocol changed between preparation and scoring')
    return item


class SafeAPIError(RuntimeError):
    def __init__(self, kind, status=None):
        self.kind, self.status = kind, status
        super().__init__(f'{kind}' + (f' (HTTP {status})' if status else ''))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class APIJudge:
    def __init__(self, config):
        self.config = config
        self.model_name = config['model']
        self.last_response = None
        self.last_error = None
        parsed = urllib.parse.urlsplit(config['base_url'])
        if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Use an HTTPS API base URL without embedded credentials, query, or fragment')
        self.key = os.environ.get(config['api_key_env'], '')
        if not self.key:
            raise ValueError(f"Missing API key environment variable: {config['api_key_env']}")

    def request(self, prompt):
        payload = {'model': self.model_name, 'messages': [{'role': 'user', 'content': prompt}],
                   self.config['token_parameter']: self.config['max_output_tokens']}
        if self.config['temperature'] is not None:
            payload['temperature'] = self.config['temperature']
        if self.config['reasoning_effort'] is not None:
            payload['reasoning_effort'] = self.config['reasoning_effort']
        request = urllib.request.Request(self.config['base_url'].rstrip('/') + '/chat/completions',
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.key})
        opener = urllib.request.build_opener(NoRedirect)
        try:
            with opener.open(request, timeout=self.config['timeout_seconds']) as response:
                body = json.load(response)
        except urllib.error.HTTPError as exc:
            # Some providers echo key fragments in error bodies. Do not log the body.
            self.last_error = SafeAPIError('http_error', exc.code)
            raise self.last_error from None
        except (urllib.error.URLError, TimeoutError, OSError):
            self.last_error = SafeAPIError('connection_error')
            raise self.last_error from None
        except (ValueError, UnicodeError):
            self.last_error = SafeAPIError('invalid_api_json')
            raise self.last_error from None
        self.last_response = body
        try:
            choice = body['choices'][0]
            if choice.get('finish_reason') == 'length':
                raise SafeAPIError('output_truncated')
            if choice.get('finish_reason') != 'stop':
                raise SafeAPIError('incomplete_api_response')
            if not isinstance(body.get('model'), str) or not body['model'].strip():
                raise SafeAPIError('missing_returned_model')
            content = choice['message']['content']
            if not isinstance(content, str) or not content.strip():
                raise SafeAPIError('empty_model_content')
        except (KeyError, TypeError, IndexError, AttributeError):
            self.last_error = SafeAPIError('unexpected_api_response')
            raise self.last_error from None
        except SafeAPIError as exc:
            self.last_error = exc
            raise
        return {'content': content}

    async def _acall(self, prompt):
        return await asyncio.to_thread(self.request, prompt)


def evaluation_observation(evaluation):
    """Separate technical completion from optional descriptive numeric values."""
    failed = {'technical_complete': False, 'numeric_scope': 'NOT_AVAILABLE',
              'numeric_status': 'FAILED', 'indices': None}
    if not isinstance(evaluation, dict) or evaluation.get('_error'):
        return {**failed, 'reason': 'EVALUATION_ERROR'}
    if evaluation.get('technical_status') not in (None, 'VALID'):
        return {**failed, 'reason': 'TECHNICAL_STATUS_NOT_VALID'}
    if 'legacy_diagnostics' in evaluation:
        diagnostic = evaluation['legacy_diagnostics']
        if (evaluation.get('technical_status') != 'VALID'
                or not isinstance(diagnostic, dict)
                or not isinstance(diagnostic.get('scores'), dict)
                or evaluation.get('cce_eligible') is not False
                or evaluation.get('official_scores') is not None):
            return {**failed, 'reason': 'MALFORMED_DIAGNOSTIC_COMPLETION'}
        # A temporary numeric view never promotes these proposals to science.
        view = {'evaluation': {'scores': diagnostic['scores']}}
        scope = 'LEGACY_CONTINUOUS_DIAGNOSTIC'
        try:
            indices = protocol_scores(view)
        except ValueError as exc:
            return {'technical_complete': True, 'numeric_scope': scope,
                    'numeric_status': 'UNKNOWN', 'indices': None, 'reason': str(exc)}
        return {'technical_complete': True, 'numeric_scope': scope,
                'numeric_status': 'COMPLETE', 'indices': indices, 'reason': None}
    # Archived root-score rows keep their existing numeric contract, not approval.
    try:
        indices = protocol_scores({'evaluation': evaluation})
    except ValueError as exc:
        return {**failed, 'reason': str(exc)}
    return {'technical_complete': True, 'numeric_scope': 'ARCHIVED_SCORE_DESCRIPTIVE',
            'numeric_status': 'COMPLETE', 'indices': indices, 'reason': None}


async def run_judge(study_dir, run_dir, config, max_calls=None):
    """Fresh judge context per protocol/replicate, no automatic retries.

    Each call has a separate result file; no cache sharing between replicates.
    A real successful canary is retained as the first planned observation.
    """
    import OEQ_run_grading_new as runner
    study_dir, run_dir = Path(study_dir).resolve(), Path(run_dir).resolve()
    plan, items, schedule = load_validated_study(study_dir)
    runner.configure_question_snapshot(ROOT / plan['question_file'])
    runner.OEQ_SCORE_DIR = str(run_dir)
    probe = APIJudge(config)
    contract = {'study': plan['package_id'], 'api_settings': config,
                'scoring_contract': runner.scoring_contract(probe),
                'experiment_code_sha256': sha256_file(__file__),
                'study_manifest_sha256': sha256_file(study_dir / 'private/study_manifest.json'),
                'items_sha256': sha256_file(study_dir / 'private/items.json'),
                'schedule_sha256': sha256_file(study_dir / 'private/call_schedule.json')}
    contract_hash = ensure_manifest(run_dir / 'run', contract)
    returned_models = set()
    for saved_path in run_dir.glob('repeat_*/*.json'):
        saved = read_json(saved_path)
        validate_attempt(saved, saved_path, run_dir, items, schedule, contract_hash)
        if saved.get('api_error') or not evaluation_observation(saved.get('evaluation'))['technical_complete']:
            print('Existing failed attempt requires diagnosis; it is retained and will not be skipped.', flush=True)
            return 2
        returned_models.add(saved.get('api_metadata', {}).get('model'))
    if len(returned_models) > 1:
        raise ValueError('Saved attempts contain different returned model IDs')
    concurrency = config.get('concurrency', 1)
    if isinstance(concurrency, bool) or not isinstance(concurrency, int) or not 1 <= concurrency <= 8:
        raise ValueError('Judge concurrency must be an integer between 1 and 8')

    async def collect_one(task):
        path = run_dir / f"repeat_{task['repeat']:02d}/{task['item_id']}.json"
        item = items[task['item_id']]
        judge = APIJudge(config)
        started = datetime.now(timezone.utc).isoformat()
        result = await runner.evaluate_response_with_teacher(
            judge, item['question'], item['protocol'], {}, {'question_id': item['question_id']}, '')
        observation = evaluation_observation(result)
        envelope = {'item_id': item['item_id'], 'repeat': task['repeat'],
                    'run_contract_sha256': contract_hash, 'started_at': started,
                    'completed_at': datetime.now(timezone.utc).isoformat(),
                    'protocol_sha256': item['protocol_sha256'], 'evaluation': result,
                    'numeric_scope': observation['numeric_scope'],
                    'numeric_status': observation['numeric_status'],
                    'api_metadata': {key: judge.last_response.get(key) for key in
                                     ('id', 'model', 'system_fingerprint', 'usage', 'created')}
                    if isinstance(judge.last_response, dict) else {},
                    'api_error': {'kind': judge.last_error.kind, 'http_status': judge.last_error.status}
                    if judge.last_error else None}
        write_json(path, envelope)
        print(json.dumps({'repeat': task['repeat'], 'item_id': item['item_id'],
                          'status': 'diagnostic_complete' if observation['technical_complete'] else 'failed'}, ensure_ascii=False), flush=True)
        # Stop on transport/authentication failures or malformed/truncated output;
        # diagnose before spending on the rest of the frozen schedule.
        if judge.last_error or not observation['technical_complete']:
            print('Run stopped after failed canary/attempt; inspect the recorded status before resuming.', flush=True)
            return False
        returned_models.add(envelope['api_metadata'].get('model'))
        if len(returned_models) > 1:
            print('Run stopped: provider returned a different model ID; attempts are preserved.', flush=True)
            return False
        return True

    pending = [task for task in schedule if not
               (run_dir / f"repeat_{task['repeat']:02d}/{task['item_id']}.json").exists()]
    if max_calls is not None:
        pending = pending[:max_calls]
    for repeat in range(1, plan['planned_repeats'] + 1):
        tasks = [task for task in pending if task['repeat'] == repeat]
        for offset in range(0, len(tasks), concurrency):
            # Launch in frozen order; finish this batch before another batch/round.
            # A failure stops new batches. Already dispatched calls are preserved.
            outcomes = await asyncio.gather(*(collect_one(task) for task in tasks[offset:offset + concurrency]))
            if not all(outcomes):
                return 2
    return 0


def rank(values):
    order = sorted(range(len(values)), key=lambda index: values[index])
    result = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        for index in order[start:end]:
            result[index] = (start + end - 1) / 2 + 1
        start = end
    return result


def spearman(left, right):
    if len(left) < 3 or len(set(left)) < 2 or len(set(right)) < 2:
        return None
    return statistics.correlation(rank(left), rank(right))


def quadratic_kappa(left, right, maximum=4):
    if not left:
        return None
    n = len(left)
    observed = sum((a - b) ** 2 for a, b in zip(left, right)) / n
    counts_a, counts_b = Counter(left), Counter(right)
    expected = sum(counts_a[a] * counts_b[b] * (a - b) ** 2
                   for a in range(maximum + 1) for b in range(maximum + 1)) / n ** 2
    return 1 - observed / expected if expected else None


def bootstrap_mean_ci(values, seed=20260921, draws=5000):
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(draws))
    return [means[int(draws * 0.025)], means[min(draws - 1, int(draws * 0.975))]]


def read_ratings(paths, plan, assignments):
    known = {(row['reviewer_id'], row['blind_id']): row for row in assignments}
    ratings, seen, audit = {}, set(), []
    allowed = {field['key']: {value for value, _ in field['options']} for field in RATING_FIELDS}
    for path in paths:
        path = Path(path)
        if path.suffix.lower() == '.csv':
            with path.open(encoding='utf-8-sig', newline='') as f:
                rows = list(csv.DictReader(f))
        else:
            data = read_json(path)
            if data.get('package_id') != plan['package_id']:
                raise ValueError(f'Rating package mismatch: {path}')
            rows = data['ratings']
        for row in rows:
            key = (str(row.get('reviewer_id', '')), str(row.get('blind_id', '')))
            if row.get('package_id') != plan['package_id'] or key not in known:
                raise ValueError(f'Unknown/mismatched rating assignment: {key}')
            if key in seen:
                raise ValueError(f'Duplicate imported rating: {key}; import one export per reviewer')
            seen.add(key)
            for field, choices in allowed.items():
                value = str(row.get(field, '')).strip()
                if value and value not in choices:
                    raise ValueError(f'Invalid rating value {field} for {key}')
            value = str(row.get('overall_feasibility', '')).strip()
            reason = str(row.get('rationale', '')).strip()
            status = 'rated' if value in {'0', '1', '2', '3', '4'} and reason else 'unassessable' if value == 'U' else 'incomplete'
            if value == 'U' and not str(row.get('unable_reason', '')).strip():
                status = 'incomplete'
            audit.append({'reviewer_id': key[0], 'blind_id': key[1], 'status': status})
            if status == 'rated':
                ratings[key] = {**row, 'overall_numeric': int(value), **known[key]}
    return ratings, audit


def analyze(study_dir, run_dir=None, rating_paths=()):
    study_dir = Path(study_dir).resolve()
    plan, by_id, schedule = load_validated_study(study_dir)
    items = list(by_id.values())
    assignments = read_json(study_dir / 'private/blinding_key.json')
    attempts, valid, completed = [], defaultdict(list), defaultdict(list)
    if run_dir:
        run_dir = Path(run_dir)
        manifest = read_json(str(run_dir / 'run') + '.manifest.json')
        if json_hash(manifest['contract']) != manifest['contract_sha256']:
            raise ValueError('Judge run manifest hash mismatch')
        if manifest['contract']['study'] != plan['package_id']:
            raise ValueError('Judge run belongs to another study')
        for name, relative in [('items_sha256', 'items.json'), ('schedule_sha256', 'call_schedule.json'),
                               ('study_manifest_sha256', 'study_manifest.json')]:
            if manifest['contract'][name] != sha256_file(study_dir / 'private' / relative):
                raise ValueError('Frozen study changed since the judge run')
        for path in sorted(run_dir.glob('repeat_*/*.json')):
            row = read_json(path)
            validate_attempt(row, path, run_dir, by_id, schedule, manifest['contract_sha256'])
            attempts.append(row)
            if row.get('api_error'):
                continue
            observation = evaluation_observation(row.get('evaluation'))
            if not observation['technical_complete']:
                continue
            observed_row = {**row, 'numeric_scope': observation['numeric_scope'],
                            'numeric_status': observation['numeric_status'],
                            'numeric_reason': observation['reason']}
            completed[row['item_id']].append(observed_row)
            if observation['indices'] is not None:
                valid[row['item_id']].append({**observed_row, 'indices': observation['indices']})
    per_item = []
    for item in items:
        entries = valid[item['item_id']]
        technical_entries = completed[item['item_id']]
        repeats = [row['repeat'] for row in technical_entries]
        if len(set(repeats)) != len(repeats) or any(not 1 <= repeat <= 3 for repeat in repeats):
            raise ValueError('Duplicate or unplanned replicate')
        values = [100 * row['indices']['I_A'] for row in entries]
        per_item.append({'item_id': item['item_id'], 'question_id': item['question_id'],
                         'model': item['model'], 'setting': item['setting'],
                         'n_technical_complete_repeats': len(technical_entries),
                         'n_numeric_unknown_repeats': len(technical_entries) - len(values),
                         'n_valid_repeats': len(values),
                         'mean_I_A': statistics.fmean(values) if values else None,
                         'sd_I_A': statistics.stdev(values) if len(values) >= 2 else None,
                         'range_I_A': max(values) - min(values) if len(values) >= 2 else None,
                         'distinct_extracted_methods': len({row['evaluation'].get('meta_data', {}).get('target_method') for row in entries}) if values else None})
    metrics_by_id = {row['item_id']: row for row in per_item}
    conditions = []
    for setting in SETTINGS[1:]:
        differences = []
        for selection in plan['selection']:
            paired = {item['setting']: metrics_by_id[item['item_id']] for item in items
                      if item['question_id'] == selection['question_id'] and item['model'] == selection['model']}
            if paired['1-shot']['n_valid_repeats'] == 3 and paired[setting]['n_valid_repeats'] == 3:
                differences.append(paired[setting]['mean_I_A'] - paired['1-shot']['mean_I_A'])
        conditions.append({'contrast': setting + ' vs 1-shot', 'n_complete_scenario_pairs': len(differences),
                           'mean_delta_points': statistics.fmean(differences) if differences else None,
                           'scenario_bootstrap_ci95': bootstrap_mean_ci(differences)})
    ratings, audit = read_ratings(rating_paths, plan, assignments)
    primary = {(row['reviewer_id'], row['item_id']): row['overall_numeric']
               for row in ratings.values() if not row['is_repeat']}
    shared = sorted(item_id for item_id in by_id if ('A', item_id) in primary and ('B', item_id) in primary)
    left, right = [primary['A', item_id] for item_id in shared], [primary['B', item_id] for item_id in shared]
    duplicate_checks = []
    for reviewer in ('A', 'B'):
        pairs = [(primary.get((reviewer, row['item_id'])), row['overall_numeric'])
                 for row in ratings.values() if row['reviewer_id'] == reviewer and row['is_repeat']]
        pairs = [(a, b) for a, b in pairs if a is not None]
        duplicate_checks.append({'reviewer_id': reviewer, 'n_pairs': len(pairs),
                                 'exact_agreement': sum(a == b for a, b in pairs) / len(pairs) if pairs else None,
                                 'mean_absolute_difference_0_4': statistics.fmean(abs(a - b) for a, b in pairs) if pairs else None})
    judge_human_ids = [item_id for item_id in shared if metrics_by_id[item_id]['n_valid_repeats'] == 3]
    human_means = {item_id: (primary['A', item_id] + primary['B', item_id]) / 2 for item_id in shared}
    correspondence = spearman([metrics_by_id[item_id]['mean_I_A'] for item_id in judge_human_ids],
                              [human_means[item_id] for item_id in judge_human_ids])
    human_contrasts = []
    for setting in SETTINGS[1:]:
        human_deltas, matched_human, matched_judge = [], [], []
        for selection in plan['selection']:
            group = {item['setting']: item['item_id'] for item in items
                     if item['question_id'] == selection['question_id'] and item['model'] == selection['model']}
            baseline_id, treatment_id = group['1-shot'], group[setting]
            if baseline_id not in human_means or treatment_id not in human_means:
                continue
            delta = human_means[treatment_id] - human_means[baseline_id]
            human_deltas.append(delta)
            if metrics_by_id[baseline_id]['n_valid_repeats'] == 3 and metrics_by_id[treatment_id]['n_valid_repeats'] == 3:
                matched_human.append(delta)
                matched_judge.append(metrics_by_id[treatment_id]['mean_I_A'] - metrics_by_id[baseline_id]['mean_I_A'])
        non_tied = [(h, j) for h, j in zip(matched_human, matched_judge) if h != 0 and abs(j) > 1e-9]
        human_contrasts.append({
            'contrast': setting + ' vs 1-shot', 'n_human_scenario_pairs': len(human_deltas),
            'mean_human_delta_0_4': statistics.fmean(human_deltas) if human_deltas else None,
            'scenario_bootstrap_ci95_0_4': bootstrap_mean_ci(human_deltas),
            'n_judge_human_scenario_pairs': len(matched_human),
            'delta_rank_correlation': spearman(matched_human, matched_judge),
            'n_non_tied_direction_pairs': len(non_tied),
            'direction_concordance_non_tied': sum((h > 0) == (j > 0) for h, j in non_tied) / len(non_tied) if non_tied else None,
            'n_human_ties_in_matched_pairs': sum(delta == 0 for delta in matched_human),
            'n_judge_ties_in_matched_pairs': sum(abs(delta) <= 1e-9 for delta in matched_judge),
        })
    variation_rows = [row for row in per_item if row['n_valid_repeats'] == 3]
    complete_count = sum(len(v) for v in completed.values())
    numeric_count = sum(len(v) for v in valid.values())
    numeric_scopes = sorted({row['numeric_scope'] for entries in completed.values() for row in entries})
    summary = {
        'package_id': plan['package_id'], 'scope': plan['scope'],
        'numeric_scope': 'LEGACY_CONTINUOUS_DIAGNOSTIC' if 'LEGACY_CONTINUOUS_DIAGNOSTIC' in numeric_scopes else 'ARCHIVED_SCORE_DESCRIPTIVE' if numeric_scopes else 'NOT_COLLECTED',
        'numeric_scopes': numeric_scopes,
        'scientific_validation': 'NOT_ESTABLISHED_FROM_NUMERIC_DIAGNOSTICS',
        'scientific_accuracy': None,
        'judge_attempts': len(attempts), 'judge_valid_results': complete_count,
        'judge_technical_complete_results': complete_count,
        'judge_failed_results': len(attempts) - complete_count,
        'judge_complete_numeric_results': numeric_count,
        'judge_numeric_unknown_results': complete_count - numeric_count,
        'returned_model_counts': dict(Counter(row.get('api_metadata', {}).get('model') for row in attempts)),
        'judge_protocols_with_all_3_repeats': sum(row['n_technical_complete_repeats'] == 3 for row in per_item),
        'judge_protocols_with_all_3_numeric_repeats': len(variation_rows), 'planned_judge_calls': 108,
        'pooled_within_protocol_sd_I_A_points': math.sqrt(statistics.fmean(row['sd_I_A'] ** 2 for row in variation_rows)) if variation_rows else None,
        'median_within_protocol_range_I_A_points': statistics.median(row['range_I_A'] for row in variation_rows) if variation_rows else None,
        'protocols_with_extracted_method_disagreement': sum(row['distinct_extracted_methods'] > 1 for row in variation_rows),
        'condition_contrasts': conditions,
        'human_imported_records': len(audit), 'human_status_counts': dict(Counter(row['status'] for row in audit)),
        'human_common_unique_protocols': len(shared),
        'human_quadratic_weighted_kappa_0_4': quadratic_kappa(left, right),
        'human_exact_agreement': sum(a == b for a, b in zip(left, right)) / len(left) if left else None,
        'human_duplicate_consistency': duplicate_checks,
        'judge_human_complete_protocols': len(judge_human_ids), 'judge_human_spearman': correspondence,
        'human_condition_contrasts': human_contrasts,
        'interpretation': 'Continuous numeric values are descriptive diagnostics, not independent scientific approval. Technical completion does not require a complete numeric vector. Repeatability and human validity are separate. No collected result is imputed; a reliable judge can still be wrong. Different human/model scales are compared by rank, not numerical agreement.',
    }
    out = study_dir / 'analysis'
    write_json(out / 'status_and_results.json', summary)
    write_json(out / 'human_import_audit.json', audit)
    (out / 'per_protocol_repeat_scores.csv').write_bytes(csv_text(per_item, list(per_item[0])).encode('utf-8'))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def main():
    os.chdir(ROOT)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare', help='Offline: freeze scenarios and produce blinded reviewer packets')
    prep.add_argument('--study-dir', required=True)
    prep.add_argument('--seed', type=int, default=20260921)
    run = commands.add_parser('run', help='Online: run independent repeated judge calls; uses API credentials')
    run.add_argument('--study-dir', required=True)
    run.add_argument('--run-dir', required=True)
    run.add_argument('--model', required=True)
    run.add_argument('--base-url', default='https://api.openai.com/v1')
    run.add_argument('--api-key-env', default='OPENAI_API_KEY')
    run.add_argument('--temperature', type=float, default=0.0)
    run.add_argument('--omit-temperature', action='store_true', help='Do not send temperature for reasoning models that disallow it')
    run.add_argument('--reasoning-effort', choices=['none', 'low', 'medium', 'high', 'xhigh'], default=None)
    run.add_argument('--max-output-tokens', type=int, default=6000)
    run.add_argument('--token-parameter', choices=['max_completion_tokens', 'max_tokens'], default='max_completion_tokens')
    run.add_argument('--timeout-seconds', type=int, default=180)
    run.add_argument('--max-calls', type=int, default=None, help='Use 1 for a canary; successful calls count toward the frozen schedule')
    run.add_argument('--concurrency', type=int, choices=range(1, 9), default=1)
    analysis = commands.add_parser('analyze', help='Offline: analyze actual collected scores and ratings')
    analysis.add_argument('--study-dir', required=True)
    analysis.add_argument('--run-dir')
    analysis.add_argument('--ratings', nargs='*', default=[])
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.study_dir, args.seed)
    elif args.command == 'analyze':
        analyze(args.study_dir, args.run_dir, args.ratings)
    else:
        config = {key: getattr(args, key) for key in ('model', 'base_url', 'api_key_env', 'temperature',
                  'reasoning_effort', 'max_output_tokens', 'token_parameter', 'timeout_seconds', 'concurrency')}
        if args.omit_temperature:
            config['temperature'] = None
        if args.max_output_tokens < 1 or args.timeout_seconds < 1 or args.max_calls is not None and args.max_calls < 1:
            parser.error('Token/time/call limits must be positive')
        return asyncio.run(run_judge(args.study_dir, args.run_dir, config, args.max_calls))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
