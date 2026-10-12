"""Actual FPC08 source-key lookup comparison; no model calls or raw edits."""
import contextlib
import io
import json
import sys
from pathlib import Path
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]
import cce_generation_confirmation_v2 as confirm
import cce_fieldwise_scoring_v3 as fw
import cce_scales_source_key_alias_v1 as alias


def main():
    out = confirm.budget.OUT / 'scales_source_key_alias_v1' / 'actual_01'
    out.mkdir(parents=True, exist_ok=False)
    j, g = confirm.j, confirm.g
    row = next(r for r in j.read(confirm.OUT / 'matrix.json') if r['anonymous_answer_id'] == 'FPC08')
    case = next(c for c in j.read(confirm.OUT / 'cases.json')['cases'] if c['anonymous_answer_id'] == 'FPC08')
    terminal_path = confirm.OUT / 'run/trials' / (row['planned_trial_id'] + '.json')
    terminal = j.read(terminal_path)
    confirm.base.verify_bindings(terminal['bound_artifacts'] + list(row['assets'].values()))
    attempt = confirm.OUT / 'run/attempts' / (row['planned_trial_id'] + '_1')
    raw = (attempt / 'raw_response.txt').read_text(encoding='utf8')
    doc = j.read(row['assets']['source_document']['path'])
    assert doc == g.document(case['model_response'], g.source_id_for_case(case))
    checks = []
    names = ['ScaleS', 'Scale S', 'Scale-S', 'SCALE (ScaleS)', 'SCALE', 'ScaleSQ', 'AbScale', 'ChemScale', 'ScaleS2', 'ScaleS + CUBIC', None]
    expected = [alias.SOURCE_KEY] * 4 + [None] * 7
    original = alias.integrity._SOURCE_KEY_ALIASES
    with alias.source_key_alias():
        for name, target in zip(names, expected):
            actual = alias.integrity.resolve_method(name, [alias.SOURCE_KEY, 'CUBIC'])
            assert actual == target, (name, actual, target)
            checks.append(dict(name=name, resolved=actual, expected=target))
        assert alias.integrity.resolve_method('ScaleS', ['ScaleS', alias.SOURCE_KEY]) == 'ScaleS'
        assert alias.integrity.method_identity('ScaleS', [alias.SOURCE_KEY], [{'id':'s1','method_name':'ScaleS','quote':'ScaleS'}])['status'] == 'COMPOSITE_UNREVIEWED'
    assert alias.integrity._SOURCE_KEY_ALIASES is original
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        conversion = fw.convert(raw, doc, case)
        before = fw.score_conversion(case, conversion, row['step'])
        after = alias.score_with_alias(fw.score_conversion, case, conversion, row['step'])
    assert before['metrics'] == terminal['metrics']
    assert all(before['metrics'][k] == after['metrics'][k] for k in fw.numeric.DIRECT + ['sr', 'sp', 'Com', 'Cor'])
    change = {k: {'before': before['metrics'][k], 'after': after['metrics'][k]} for k in fw.numeric.METRICS if before['metrics'][k] != after['metrics'][k]}
    dependencies = [Path(__file__), Path(alias.__file__), ROOT/'evaluator_integrity.py', ROOT/'build_rag_context.py', ROOT/'dataset/Q+AR/src/model_space_signed.json', ROOT/'KnowledgeBase/method_ri_ref.json', ROOT/'KnowledgeBase/time_kb.json']
    for name, data in [('before.json', before), ('after.json', after), ('conversion.json', conversion), ('checks.json', checks)]:
        confirm.write(out/name, data)
    summary = dict(version=alias.VERSION, answer_id='FPC08', source_method='ScaleS', authored_key=alias.SOURCE_KEY,
        before=before['metrics'], after=after['metrics'], changes=change,
        new_model_calls=0, source_or_raw_modified=False, original_confirmation_unchanged=True,
        scientific_acceptance=False, exact_alias_checks=13,
        interpretation='Posthoc identity lookup correction, not a new judge observation or an added scientific reference.')
    confirm.write(out/'summary.json', summary)
    confirm.write(out/'verification.json', dict(actual_command=[sys.executable,*sys.argv], dependencies=[confirm.bind(p) for p in dependencies],
        input_bindings=[confirm.bind(terminal_path),confirm.bind(attempt/'raw_response.txt'),row['assets']['source_document']], all_checks_passed=True))
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
