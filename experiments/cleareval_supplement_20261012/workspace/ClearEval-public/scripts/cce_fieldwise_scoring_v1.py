"""Score existing v11 returns with field-local extraction fixes.

No model request is made. The original rubric, numerical functions and SR/SP
are reused. A missing label relationship does not erase a supported one, and a
missing physical property does not erase an extracted operation or its time.
"""
from __future__ import annotations

import copy
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

import cce_round2_runner_v11 as base
import cce_grounded_extraction_fieldwise_base_v1 as fieldwise_base
import cce_operation_coverage_scope_diagnostic_v1 as operation_scope
import cce_duration_scope_fix_v1 as duration_scope
import cce_noncore_time_scope_fix_v1 as noncore_scope
import cce_label_occurrence_diagnostic_v1 as labels

ground = base.grounded
numeric = base.scoring
VERSION = "fieldwise-scoring-v1"
TIME_SCOPE = "initial_core_clearing_to_first_imaging_ready"


def separate_empty_modules(audit, doc):
    """An omitted module is a completeness issue, not an unextracted operation."""
    coverage = audit["resolved"]["coverage"]
    changes = []
    units = doc["units"]
    heading = re.compile(r'^\s*(?:#{1,6}\s*)?(?:(\d+(?:\.\d+)*)(?:[.)])?|[-*+])\s+(.+?)\s*$')
    titles = re.compile(r'^(?:(?:refractive\s+index\s*(?:\(RI\))?|RI)\s+matching(?:\s+and\s+clearing)?|storage(?:\s+and\s+pre[- ]imaging(?:\s+treatment)?)?)$', re.I)
    recognized, empty = {}, set()
    for index, unit in enumerate(units):
        match = heading.fullmatch(unit['text'].strip())
        if not match or not titles.fullmatch(match[2]):
            continue
        recognized[unit['unit_id']] = unit
        following = next((u for u in units[index + 1:] if u['text'].strip()), None)
        next_heading = heading.fullmatch(following['text'].strip()) if following else None
        # A following bullet is conservatively treated as content unless it is
        # itself a recognized section title. A real child action stays present.
        if following is None or (next_heading and (titles.fullmatch(next_heading[2])
                or (match[1] and next_heading[1] and next_heading[1].count('.') <= match[1].count('.')))):
            empty.add(unit['unit_id'])
    # Section labels are not instructions, whether or not their module has a
    # body. Preserve the original candidate/record alongside the derived view.
    for row in audit['inventory']:
        unit = recognized.get(row['span']['unit_id'])
        if row['kind'] == 'operation_record_lead' and unit and row['span']['quote'].strip() == unit['text'].strip():
            original = copy.deepcopy(row)
            row['kind'] = 'section_heading_lead'
            row['coverage_state'] = 'classified_section_heading_not_operation'
            changes.append({'interpretation': 'section_heading_not_operation', 'unit_id': unit['unit_id'], 'original_inventory_record': original})
    removed = [o for o in audit['resolved']['operations'] if o['operation']['unit_id'] in recognized
        and o['operation']['quote'].strip() == recognized[o['operation']['unit_id']]['text'].strip()]
    if removed:
        ids = {o['id'] for o in removed}
        audit['resolved']['operations'] = [o for o in audit['resolved']['operations'] if o['id'] not in ids]
        audit['resolved']['timeline']['operation_ids'] = [i for i in audit['resolved']['timeline']['operation_ids'] if i not in ids]
        changes.extend({'interpretation': 'returned_heading_not_operation', 'unit_id': o['operation']['unit_id'],
            'original_returned_record': copy.deepcopy(o), 'raw_record_preserved': True} for o in removed)
    if coverage['core_time_operations'] == 'complete' or not coverage['unresolved']:
        return changes
    for unresolved in coverage["unresolved"]:
        source = unresolved["evidence"]
        unit = recognized.get(source['unit_id'])
        if not unit or source['unit_id'] not in empty or source['quote'].strip() != unit['text'].strip():
            return changes
    audit["original_reported_core_coverage"] = coverage["core_time_operations"]
    coverage["core_time_operations"] = "complete"
    changes.extend({'unit_id': x['evidence']['unit_id'], 'interpretation': 'empty_module_no_reported_operation',
        'original_unresolved': copy.deepcopy(x)} for x in coverage['unresolved'])
    return changes


def apply_time_rubric(audit):
    """Retain the original rubric's explicit overnight-to-eight-hours convention."""
    changes = []
    for operation in audit["resolved"]["operations"]:
        parsed = operation["parsed_duration"]
        if parsed.get("state") == "unspecified_overnight" and operation.get("duration"):
            revised = ground.duration_value(operation["duration"]["quote"], overnight_hours=8)
            changes.append({"operation_id": operation["id"], "original_parsed_duration": copy.deepcopy(parsed),
                "rubric_parsed_duration": revised, "rule": "original_teacher_rubric_section_3.2"})
            operation["parsed_duration"] = revised
    return changes


def project_first_pass(audit):
    """Score initial core processing; later repeated-imaging work stays separate."""
    projection = ground.project_legacy(audit)
    time = projection["time_calculation"]
    time["primary_time_scope"] = TIME_SCOPE
    time["overnight_policy"] = "Original rubric: overnight is eight hours by convention, not a measured duration."
    endpoint_issue = "conditional_operations_require_endpoint_resolution"
    if endpoint_issue in time["issues"]:
        time["issues"] = [issue for issue in time["issues"] if issue != endpoint_issue]
        time["later_processing_reported_separately"] = True
        bounds = time["initial_scope_candidate_bounds_hours"]
        if not time["issues"] and bounds and bounds[0] == bounds[1]:
            time["total_hours"] = bounds[0]
            projection["extraction"]["clearing_total_time_hours"] = bounds[0]
            projection["component_input_state"]["s_time"] = "available_provisional"
    time["endpoint_scope"] = "The primary score covers the reported initial core processing. Conditional later operations and their time bounds are retained separately."
    return projection


def convert(raw, doc, case=None):
    """Keep the raw return and derive the inputs used by each scoring component."""
    conversion = fieldwise_base.convert(raw, doc)
    audit, record_changes = operation_scope.derive_audit(conversion["source_audit"], doc)
    audit, duration_changes = duration_scope.derive_audit(audit, doc)
    audit, noncore_changes = noncore_scope.derive_audit(audit, doc)
    empty_module_changes = separate_empty_modules(audit, doc)
    rubric_time_changes = apply_time_rubric(audit)
    conversion["source_audit"] = audit
    projection = project_first_pass(audit)
    conversion["legacy_projection"] = projection
    conversion["legacy_runner_payload"] = {
        "scores": copy.deepcopy(conversion["wire_payload"]["scores"]),
        "extraction": copy.deepcopy(projection["extraction"]),
    }
    conversion["legacy_runner_content"] = ground.canonical(conversion["legacy_runner_payload"])
    conversion["label_occurrence_projection"] = labels.derive_label_projection(conversion, doc, case)
    conversion["fieldwise_processing"] = {
        "version": VERSION,
        "wire_version": ground.VERSION,
        "operation_records_changed": [row for row in record_changes if row["changed"]],
        "duration_candidates_reclassified": duration_changes,
        "noncore_time_scope_changes": noncore_changes,
        "empty_modules_are_protocol_omissions": empty_module_changes,
        "original_rubric_time_conventions": rubric_time_changes,
        "primary_time_scope": TIME_SCOPE,
        "raw_response_modified": False,
        "new_model_requests": 0,
    }
    return conversion


def score_conversion(case, conversion, step):
    """Run original non-label calculations and the occurrence-preserving label adapter."""
    legacy = numeric.score_conversion(case, conversion, base.BACKEND, step)
    runner, registry = numeric.runtime()
    meta = runner.QUESTION_META_KB[registry.questions[str(case["question_id"])]["question_id"]]
    label_result = labels.score_label_occurrences(
        conversion["label_occurrence_projection"], runner,
        legacy["quantitative_data"], legacy["user_preference_vector"],
        meta.get("marker_query_targets") or [],
    )
    components = copy.deepcopy(legacy["component_gated_proposals"])
    components["s_label"] = label_result["s_label"]
    values = numeric.derive(components, step, True)
    return {
        "status": "scored_with_field_local_dependencies",
        "processing_version": VERSION,
        "raw_response_sha256": conversion["raw_response_sha256"],
        "source_binding": conversion["source_audit"]["source_binding"],
        "metrics": values,
        "complete_numeric_CCE": all(numeric.finite(values[k]) for k in ["Com", "Cor", "Eff"]),
        "component_numeric_proposals": components,
        "quantitative_data": legacy["quantitative_data"],
        "user_preference_vector": legacy["user_preference_vector"],
        "original_nonlabel_EGES": {k: legacy["original_EGES_replay"][k] for k in ["s_method", "s_trans", "s_time"]},
        "occurrence_label_calculation": label_result,
        "legacy_dictionary_label_before_occurrence_adapter": {
            k: legacy["original_EGES_replay"][k] for k in labels.CHANNELS + ["s_label"]
        },
        "numeric_formula_definition": numeric.definition(),
        "new_model_requests": 0,
        "analysis_scope": "posthoc_reprocessing_of_actual_public_returns",
        "expert_confirmed": False,
    }


def evaluate(raw, doc, case, step):
    conversion = convert(raw, doc, case)
    return conversion, score_conversion(case, conversion, step)
