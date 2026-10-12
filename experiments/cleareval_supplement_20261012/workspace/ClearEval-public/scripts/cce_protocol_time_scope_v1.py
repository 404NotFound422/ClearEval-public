"""Posthoc source-scope corrections; raw returns and original formulas stay intact.

An overview is not another operation. A source-described antibody wash is not
made core by a returned phase label. Optional initial work remains a branch.
"""
import copy
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import cce_fieldwise_scoring_v6 as fw

g = fw.ground
VERSION = "posthoc-protocol-time-scope-v1"
TOP = re.compile(r"^\s*(?:#{1,6}\s*)?(\d+)[.)]?\s+([^\n]+?)\s*$")
CHILD = re.compile(r"^\s*(\d+)\.\d+(?:\.\d+)*\s+")
LABEL = re.compile(r"antibod|immuno|stain|label", re.I)
WASH = re.compile(r"\bwash(?:ing|es)?\b|\brins(?:e|ing)\b", re.I)
PBS = re.compile(r"\bPBS(?:-T)?\b|\bPBT\b|phosphate[- ]buffered\s+saline", re.I)
CORE = re.compile(r"delipid|decalcif|decolor|dehydrat|refractive\s+index\s+match|\bRI[- ]?match|equilibrat|clearing\s+(?:reagent|solution|transition|treatment)|\b(?:DBE|THF|methanol|ethanol|dichloromethane)\b", re.I)
UNCERTAIN = re.compile(r"\b(?:not|without|either|instead|alternative)\b", re.I)
OPTIONAL = re.compile(r"\boptional\b|\bskip\s+if\b", re.I)
FUTURE = re.compile(r"repeat(?:ed)?\s+imaging|after\s+(?:long[- ]term\s+)?storage|future|subsequent|later", re.I)
ACTION_IN_OVERVIEW = re.compile(r"\b(?:must|should|incubat\w*|wash\w*|treat\w*|immerse|transfer)\b", re.I)


def section(doc, span):
    units = doc["units"]
    index = next((i for i, u in enumerate(units) if u["unit_id"] == span["unit_id"]), None)
    if index is None:
        return None
    child = CHILD.match(span["quote"])
    if not child:
        return None
    for pos in range(index - 1, -1, -1):
        match = TOP.fullmatch(units[pos]["text"].strip().strip("*"))
        if match:
            if match[1] != child[1]:
                return None
            end = next((i for i in range(pos + 1, len(units)) if TOP.fullmatch(units[i]["text"].strip().strip("*"))), len(units))
            previous = next((i for i in range(pos - 1, -1, -1) if TOP.fullmatch(units[i]["text"].strip().strip("*"))), None)
            return {"title": units[pos], "body": units[pos + 1:end],
                    "previous": units[previous:pos] if previous is not None else []}
    return None


def wash_support(op, doc):
    span = op["operation"]
    unit = next(u for u in doc["units"] if u["unit_id"] == span["unit_id"])
    if span["quote"].strip() != unit["text"].strip() or doc["text"][span["start"]:span["end"]] != span["quote"]:
        return None
    text = span["quote"]
    if not PBS.search(text) or CORE.search(text) or UNCERTAIN.search(text):
        return None
    sec = section(doc, span)
    if not sec:
        return None
    title = sec["title"]["text"]
    if LABEL.search(title) and (WASH.search(text) or WASH.search(title)):
        return {"basis": "explicit_labeling_section_routine_buffer_wash", "evidence": [sec["title"], span]}
    if WASH.search(title) and not CORE.search(title):
        prior = sec["previous"]
        if prior and LABEL.search(prior[0]["text"]) and any(LABEL.search(u["text"]) and re.search(r"incubat|stain|label", u["text"], re.I) for u in prior[1:]):
            return {"basis": "routine_buffer_wash_immediately_after_source_labeling_section", "evidence": [*prior, sec["title"], span]}
    return None


def first_imaging_ri_support(op, doc):
    text = op['operation']['quote']
    if op['phase'] != 'imaging' or FUTURE.search(text) or OPTIONAL.search(text) or UNCERTAIN.search(text) or LABEL.search(text):
        return None
    if not re.search(r'\b(?:prior\s+to|before)\s+imaging\b', text, re.I):
        return None
    if not re.search(r'\bincubat\w*\b', text, re.I) or not re.search(r'\bto\s+reduce\s+refractive\s+index\s+mismatch\b', text, re.I):
        return None
    span = op['operation']; unit = next(u for u in doc['units'] if u['unit_id'] == span['unit_id'])
    if span['quote'].strip() != unit['text'].strip():
        return None
    return {'basis': 'explicit_incubation_for_RI_adjustment_before_imaging_not_mounting_or_repeated_imaging', 'evidence': [copy.deepcopy(span)]}


def label_metadata_support(row, audit, doc):
    span = row['span']; units = doc['units']; index = next(i for i,u in enumerate(units) if u['unit_id'] == span['unit_id'])
    if not re.match(r'\s*\(?\s*(?:Temperature|Time)\s*:', units[index]['text'], re.I):
        return None
    prior = index - 1
    while prior >= 0 and (not units[prior]['text'].strip() or re.match(r'\s*[-*•]\s+', units[prior]['text'])):
        prior -= 1
    if prior < 0:
        return None
    action = units[prior]
    if not re.search(r'\bincubat\w*\s+with\s+(?:primary|secondary)\s+antibodies\s*:', action['text'], re.I):
        return None
    if any(CORE.search(u['text']) or UNCERTAIN.search(u['text']) for u in units[prior:index+1]):
        return None
    matching = [o for o in audit['resolved']['operations'] if o['operation']['unit_id'] == action['unit_id'] and o['phase'] in {'labeling_preparation','antibody_incubation','staining'}]
    if len(matching) != 1:
        return None
    return {'basis': 'trailing_time_metadata_of_source_antibody_list', 'operation_id': matching[0]['id'], 'evidence': copy.deepcopy(units[prior:index+1])}


def derive_audit(original, doc):
    if original["source_binding"]["source_id"] != doc["source_id"] or original["source_binding"]["answer_sha256"] != doc["answer_sha256"] or g.rawsha(doc["text"]) != doc["answer_sha256"]:
        raise ValueError("SOURCE_IDENTITY_MISMATCH")
    audit = copy.deepcopy(original)
    changes, optional = [], []
    for op in audit["resolved"]["operations"]:
        support = wash_support(op, doc)
        if support and op["phase"] != "routine_wash":
            changes.append({"type": "source_phase_correction", "operation_id": op["id"], "original_phase": op["phase"],
                            "derived_phase": "routine_wash", **copy.deepcopy(support)})
            op["phase"] = "routine_wash"
        ri_support = first_imaging_ri_support(op, doc)
        if ri_support:
            changes.append({'type':'source_phase_and_first_pass_correction','operation_id':op['id'],
                            'original_phase':op['phase'],'original_execution_scope':op['execution_scope'],
                            'derived_phase':'ri_matching','derived_execution_scope':'initial',**ri_support})
            op['phase'] = 'ri_matching';op['execution_scope'] = 'initial'
            op['scope_gate']['conditional_cue_detected'] = False
        sec = section(doc, op["operation"])
        if sec and OPTIONAL.search(sec["title"]["text"]) and not FUTURE.search(sec["title"]["text"] + op["operation"]["quote"]) and op["phase"] in g.INCLUDE:
            old = {k: copy.deepcopy(op.get(k)) for k in ["execution_scope", "scope_gate", "condition_evidence"]}
            op["execution_scope"] = "conditional_or_future"
            op["scope_gate"]["conditional_scope_supported"] = True
            op["condition_evidence"] = copy.deepcopy(sec["title"])
            op["condition_evidence"]["quote"] = sec["title"]["text"]
            optional.append(op["id"])
            changes.append({"type": "optional_initial_parent_scope", "operation_id": op["id"], "original": old,
                            "evidence": [copy.deepcopy(sec["title"]), copy.deepcopy(op["operation"])],
                            "optional_branch_selected": False})
    body_start = next((u["start"] for u in doc["units"] if re.search(r"protocol\s+steps", u["text"], re.I)), None)
    for row in audit["inventory"]:
        span = row["span"]
        if row["kind"] != "duration":
            continue
        supported = label_metadata_support(row, audit, doc)
        if supported and row['coverage_state'] != 'covered_time_evidence':
            old = copy.deepcopy(row);row['kind'] = 'excluded_noncore_duration'
            changes.append({'type':'excluded_antibody_metadata_duration','original_candidate':old,**supported})
            continue
        if body_start is None or span["start"] >= body_start:
            continue
        unit = next(u for u in doc["units"] if u["unit_id"] == span["unit_id"])
        if re.match(r"\s*\*{0,2}Justification\s*\*{0,2}\s*:", unit["text"], re.I) and not ACTION_IN_OVERVIEW.search(unit['text']):
            old = copy.deepcopy(row)
            row["kind"] = "non_additive_method_overview_duration"
            row["posthoc_scope"] = "method_rationale_before_Protocol_Steps_not_an_additional_timed_operation"
            changes.append({"type": "overview_duration_scope", "original_candidate": old,
                            "source_unit": copy.deepcopy(unit), "overview_claim_retained_not_certified": True})
    operations = audit["resolved"]["operations"]
    old_timeline = copy.deepcopy(audit["resolved"]["timeline"])
    audit["resolved"]["timeline"]["operation_ids"] = [o["id"] for o in sorted(operations, key=lambda x: x["operation"]["start"]) if o["phase"] in g.INCLUDE and o["execution_scope"] == "initial"]
    record = {"version": VERSION, "changes": changes, "optional_initial_operation_ids": optional,
              "original_derived_timeline": old_timeline, "model_raw_modified": False,
              "durations_repeats_and_reported_coverage_changed": False, "scientific_phase_validation": False}
    audit["posthoc_protocol_time_scope"] = record
    return audit, record


def project(audit):
    projection = fw.duration_scope.project_first_pass(audit)
    time = projection["time_calculation"]
    optional = audit["posthoc_protocol_time_scope"]["optional_initial_operation_ids"]
    if optional:
        time["issues"] = sorted(set(time["issues"] + ["optional_initial_core_branch_not_selected"]))
        time["total_hours"] = None
        projection["extraction"]["clearing_total_time_hours"] = None
        projection["component_input_state"]["s_time"] = "partial"
        time["optional_initial_branch_envelope_hours"] = time["initial_plus_at_most_one_conditional_execution_envelope_hours"]
    return projection
