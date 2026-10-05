"""Fine-grained audits: source binding is distinct from semantic correctness.

Error-event metrics use a frozen planned denominator and caller-declared
references. This module does not authenticate reviewers or certify science.
"""
from collections import Counter, defaultdict
from .contract import STATES
from .fidelity import text_hash, validate_span

VERSION = 'fine-grained-evaluation-v1'
UNIT_FIELDS = ('task_id', 'answer_id', 'candidate_id', 'requirement_id')
EVENT_FIELDS = UNIT_FIELDS + ('entity_id', 'condition_scope', 'polarity', 'cause_id')
REFERENCE_BASES = {'INDEPENDENT_REVIEW', 'TEXT_ARITHMETIC_REFERENCE', 'ENGINEERING_CONTROL'}


def _metric(numerator, denominator):
    return dict(numerator=numerator, denominator=denominator,
                value=numerator / denominator if denominator else None)


def audit_fact_source_bindings(package, source_texts):
    """Audit exact source locations only; do not grade canonical interpretations."""
    sources, facts = package.get('sources'), package.get('facts')
    if not isinstance(sources, list) or not isinstance(facts, list):
        raise ValueError('Source and fact arrays required')
    source_ids = [s.get('source_id') for s in sources if isinstance(s, dict)]
    if (len(source_ids) != len(sources) or len(set(source_ids)) != len(source_ids)
            or any(not isinstance(sid, str) or not sid for sid in source_ids)):
        raise ValueError('Unique source IDs required')
    source_audits = []
    for source in sources:
        sid = source['source_id']
        text = source_texts.get(sid)
        ok = isinstance(text, str) and text_hash(text) == source.get('answer_sha256')
        source_audits.append(dict(source_id=sid, full_answer_sha256_matches=ok))
    source_ok = {s['source_id']: s['full_answer_sha256_matches'] for s in source_audits}
    fact_ids = [f.get('fact_id') for f in facts if isinstance(f, dict)]
    if (len(fact_ids) != len(facts) or len(set(fact_ids)) != len(fact_ids)
            or any(not isinstance(fid, str) or not fid for fid in fact_ids)):
        raise ValueError('Unique fact IDs required')
    audits, categories = [], defaultdict(lambda: Counter())
    for fact in facts:
        sid, kind = fact.get('source_id'), fact.get('type')
        if sid not in source_ok or not isinstance(kind, str) or not kind:
            raise ValueError('Known source and fact type required')
        spans = fact.get('field_spans')
        if not isinstance(spans, list) or not spans:
            raise ValueError('At least one per-field span required')
        checks = []
        for span in spans:
            bound = False
            if isinstance(span, dict) and source_ok[sid]:
                try:
                    validate_span(source_texts[sid], {k: span[k] for k in ('start', 'end', 'quote')})
                    validate_span(source_texts[sid], dict(start=span['context_start'], end=span['context_end'],
                                       quote=span['context']))
                    bound = span['context_start'] <= span['start'] < span['end'] <= span['context_end']
                except (ValueError, KeyError, TypeError):
                    pass
            checks.append(dict(field=span.get('field') if isinstance(span, dict) else None,
                               source_bound=bound))
        complete = all(c['source_bound'] for c in checks)
        categories[kind].update(facts=1, bound_facts=int(complete), spans=len(checks),
                                bound_spans=sum(c['source_bound'] for c in checks))
        audits.append(dict(fact_id=fact['fact_id'], source_id=sid, type=kind,
            all_supplied_spans_bound=complete, field_checks=checks,
            model_proposed_reference=fact.get('model_proposed_reference') is True,
            independent_semantic_reference_eligible=False))
    return dict(schema_version=VERSION, scope='EXACT_SOURCE_BINDING_ONLY',
        source_audits=source_audits, fact_audits=audits,
        source_binding=_metric(sum(source_ok.values()), len(sources)),
        fact_binding=_metric(sum(a['all_supplied_spans_bound'] for a in audits), len(facts)),
        field_span_binding=_metric(sum(c['source_bound'] for a in audits for c in a['field_checks']),
                                   sum(len(a['field_checks']) for a in audits)),
        by_fact_type={k: dict(v) for k, v in sorted(categories.items())},
        extraction_semantic_accuracy=None, full_content_recall=None,
        scientific_accuracy=None, scientific_reference_authenticated=False)


def error_event_metrics(planned, predictions, references, *, reference_basis='INDEPENDENT_REVIEW'):
    """Exact critical-error matching, including cause and binding, with abstentions.

    case_id identifies a planned evaluation slot. Candidate/requirement/etc. in
    the emitted event must still match; case_id alone cannot credit a wrong cause
    or an event borrowed from another candidate. Optional violations are not
    critical errors. Missing requests remain in the planned denominator.
    """
    if reference_basis not in REFERENCE_BASES:
        raise ValueError('Unsupported reference basis')
    def keyed(rows):
        if not isinstance(rows, list):
            raise ValueError('Arrays required')
        out = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('case_id'), str) or not row['case_id'] or row['case_id'] in out:
                raise ValueError('Unique nonempty case IDs required')
            out[row['case_id']] = row
        return out
    plans, preds, refs = keyed(planned), keyed(predictions), keyed(references)
    if not set(preds).issubset(plans) or not set(refs).issubset(plans):
        raise ValueError('Unplanned predictions/references cannot silently change denominators')
    counters, groups, details = Counter(), defaultdict(Counter), []
    for case_id, plan in plans.items():
        if any(not isinstance(plan.get(k), str) or not plan[k] for k in UNIT_FIELDS + ('source_group',)):
            raise ValueError('Frozen unit identity and source group required')
        pred, ref = preds.get(case_id), refs.get(case_id)
        if pred is not None and (pred.get('status') not in STATES | {None}
                or type(pred.get('necessary')) is not bool):
            raise ValueError('Prediction requires four-state/null status and necessity')
        eligible = (ref is not None and ref.get('reference_basis') == reference_basis
                    and ref.get('model_proposed_reference') is not True
                    and (reference_basis != 'INDEPENDENT_REVIEW' or
                         (ref.get('independently_reviewed') is True and bool(ref.get('review_id')))))
        if eligible:
            if ref.get('status') not in STATES or type(ref.get('necessary')) is not bool:
                raise ValueError('Reference status/necessity invalid')
            if any(ref.get(k) != plan[k] for k in UNIT_FIELDS):
                raise ValueError('Reference does not align with the frozen planned unit')
            if ref['status'] == 'VIOLATED' and ref['necessary']:
                if any(not isinstance(ref.get(k), str) or not ref[k] for k in EVENT_FIELDS):
                    raise ValueError('Critical reference requires complete event/cause tuple')
        status = pred.get('status') if pred else None
        decisive = status in {'SATISFIED', 'VIOLATED'}
        missing = status is None
        reference_decisive = bool(eligible and ref['status'] in {'SATISFIED', 'VIOLATED'})
        critical = bool(eligible and ref['status'] == 'VIOLATED' and ref['necessary'])
        predicted_critical = bool(pred and status == 'VIOLATED' and pred['necessary'])
        strict = bool(critical and predicted_critical and
                      all(pred.get(k) == ref[k] for k in EVENT_FIELDS))
        count = Counter(planned=1, decisive=int(decisive), technical_failure=int(missing),
            unresolved=int(status == 'UNRESOLVED'), under_specified=int(status == 'UNDER_SPECIFIED'),
            eligible_reference=int(eligible), decisive_reference=int(reference_decisive),
            unknown_reference=int(eligible and not reference_decisive), critical_reference=int(critical),
            strict_tp=int(strict), strict_fn=int(critical and not strict),
            strict_fp=int(reference_decisive and predicted_critical and not strict),
            status_only_detected=int(critical and status == 'VIOLATED'),
            cause_or_binding_mismatch=int(critical and predicted_critical and not strict),
            false_accept=int(critical and status == 'SATISFIED'))
        counters.update(count); groups[plan['source_group']].update(count)
        details.append(dict(case_id=case_id, reference_eligible=eligible,
            prediction_status=status, critical_reference=critical, strict_event_match=strict))
    def summarize(c):
        return dict(counts=dict(c),
            strict_error_event_recall=_metric(c['strict_tp'], c['critical_reference']),
            strict_error_event_precision=_metric(c['strict_tp'], c['strict_tp'] + c['strict_fp']),
            status_only_error_recall=_metric(c['status_only_detected'], c['critical_reference']),
            critical_false_accept=_metric(c['false_accept'], c['critical_reference']),
            decisive_coverage=_metric(c['decisive'], c['planned']),
            technical_failure=_metric(c['technical_failure'], c['planned']),
            reference_coverage=_metric(c['eligible_reference'], c['planned']))
    per_group = {k: summarize(c) for k, c in sorted(groups.items())}
    group_recalls = [v['strict_error_event_recall']['value'] for v in per_group.values()
                     if v['strict_error_event_recall']['value'] is not None]
    return dict(schema_version=VERSION, reference_basis=reference_basis,
        interpretation='INDEPENDENT_REFERENCES_CALLER_DECLARED' if reference_basis == 'INDEPENDENT_REVIEW'
                       else 'FINITE_CONTROL_COUNTS_NOT_SCIENTIFIC_ACCURACY',
        reference_authentication='NOT_PERFORMED_BY_METRIC_FUNCTION',
        **summarize(counters), by_source_group=per_group,
        source_macro_strict_recall=(sum(group_recalls)/len(group_recalls) if group_recalls else None),
        source_groups_with_critical_reference=len(group_recalls), case_audits=details,
        confidence_interval=None, scientific_comparative_superiority=None)