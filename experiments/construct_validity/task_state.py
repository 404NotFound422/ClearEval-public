"""Finite task-text proposals; no protocol parser or scientific gold."""
from __future__ import annotations
from copy import deepcopy
import hashlib
import re
from .contract import digest, validate_requirements

VERSION = "provisional-task-state-v1"
INITIAL_FIXATION = "INITIAL_FIXATION"
MEMBRANE_LABEL_DIFFUSION = "MEMBRANE_LABEL_DIFFUSION"
PRE_CLEARING_INITIAL_LABEL_QC = "PRE_CLEARING_INITIAL_LABEL_QC"
LYMPHOCYTE_T_B_DISCRIMINATION = "LYMPHOCYTE_T_B_DISCRIMINATION"
FUNCTIONS = (INITIAL_FIXATION, MEMBRANE_LABEL_DIFFUSION, PRE_CLEARING_INITIAL_LABEL_QC, LYMPHOCYTE_T_B_DISCRIMINATION)
QC_COMPLETION_PATTERN = (
    r"\u72ec\u7acb(?:\u5bf9\u7167)?(?:\u5df2(?:\u7ecf)?)?\u9a8c\u8bc1(?:\u4e86)?"
    r"\u76ee\u6807(?:\u6bb5)?\u6807\u8bb0(?:\u53ca|\u4e0e|\u548c)\u80cc\u666f(?:\u5df2(?:\u7ecf)?)?(?:\u5408\u683c|\u901a\u8fc7)"
    r"|\bindependent control (?:has )?verified target label(?:ing|ling) and background (?:has )?passed\b")
ALIASES = {
    INITIAL_FIXATION: r"固定|\bfixation\b|\b(?:un)?fixed\b|\bfix\b",
    MEMBRANE_LABEL_DIFFUSION: r"膜内扩散|膜(?:内)?标记扩散|membrane(?:[- ]label)? diffusion",
    PRE_CLEARING_INITIAL_LABEL_QC: r"(?:初始|独立|透明前)[^，,。;.；\n]{0,14}(?:质控|QC)|(?:initial|independent|pre[- ]clearing)[^,.;\n]{0,28}(?:QC|quality control)" + "|" + QC_COMPLETION_PATTERN,
    LYMPHOCYTE_T_B_DISCRIMINATION: r"(?<![A-Za-z0-9_])(?:T(?![A-Za-z0-9_])\s*(?:/|and|or|versus|vs\.?|\u3001|\u548c|\u4e0e|\u6216)\s*B(?![A-Za-z0-9_])\s*(?:\u7ec6\u80de|cells?)?|T(?![A-Za-z0-9_])\s*(?:\u7ec6\u80de|cells?)\s*(?:\u548c|\u4e0e|\u53ca|\u6216|and|or|versus|vs\.?)\s*B(?![A-Za-z0-9_])\s*(?:\u7ec6\u80de|cells?))",
}
def regex(pattern):
    return re.compile(pattern, re.I)
CONDITIONAL = regex(r"若|如果|如需|必要时|假如|\bif\b|\bunless\b|\bwhen needed\b|\bconditional(?:ly)?\b")
REQUEST = regex(r"请|本方案(?:必须|应|需|要求)|本次(?:必须|应|需|要求)|\bplease\b|\b(?:this|the) (?:plan|protocol) (?:must|shall|should|requires?)\b")
ACTION = regex(r"包括|包含|安排|完成|进行|执行|加入|纳入|\binclude\b|\bperform\b|\bcomplete\b|\bschedule\b|\bcarry out\b")
EXCLUDED = regex(r"另处|其他方案|本方案不|本次不|不纳入|无需|不要求|不要|\belsewhere\b|\boutside (?:this|the) (?:plan|protocol)\b|\bdo not\b|\bnot required\b|\bno need\b")
NOT_DONE = regex(r"尚未|还未|未完成|未固定|没有完成|未经固定|\bunfixed\b|\bnot (?:yet )?(?:been )?(?:completed?|done|fixed)\b|\bhas not (?:yet )?been (?:completed|done|fixed)\b|\bincomplete\b|\bnot yet\b")
DONE = regex(r"已(?:经)?(?:完成|固定|通过)|完成了|质控合格|\balready\b|\b(?:is|was|has been) (?:completed|done|fixed)\b|\bQC passed\b|\b(?:completed|done)\b")
UNKNOWN = regex(r"未知|不明确|尚不清楚|无法确认|\bunknown\b|\bunclear\b|\bnot known\b")
GOAL_NEGATIVE = regex(r"不要求|无需|不需要|不必|\bdoes not require\b|\bnot required\b|\bno need\b|\bdo not\b")
GOAL_REQUEST = regex(r"要求|需要|必须|目标|请|\brequire[sd]?\b|\bmust\b|\bgoal\b|\bplease\b")
DISCRIMINATE = regex(r"区分|分辨|鉴别|\bdistinguish\b|\bdiscriminat(?:e|ion)\b|\bdifferentiat(?:e|ion)\b")


def _span(text, start, end):
    return dict(kind="TASK_TEXT", field="question", start=start, end=end, quote=text[start:end])


def _segments(text):
    """Carry a leading condition across commas until a contrast or sentence end."""
    for sentence in re.finditer(r"[^\u3002.;\uFF1B\n]+", text):
        conditional_span = None
        for clause in re.finditer(r"[^\uFF0C,]+", sentence.group()):
            part_start = 0
            contrasts = list(re.finditer(r"\u4F46|\u7136\u800C|\bbut\b|\bhowever\b", clause.group(), re.I))
            for contrast in contrasts + [None]:
                part_end = contrast.start() if contrast else len(clause.group())
                start = sentence.start() + clause.start() + part_start
                end = sentence.start() + clause.start() + part_end
                if text[start:end].strip():
                    if CONDITIONAL.match(text[start:end].lstrip()):
                        conditional_span = _span(text, start, end)
                    yield start, end, sentence.group(), conditional_span
                if contrast is not None:
                    conditional_span = None
                    part_start = contrast.end()


def _mentions(function, clause, sentence):
    pattern = ALIASES[function]
    if re.search(ALIASES[MEMBRANE_LABEL_DIFFUSION], sentence, re.I):
        if function == MEMBRANE_LABEL_DIFFUSION:
            pattern += r"|扩散|\bdiffusion\b"

    return list(re.finditer(pattern, clause, re.I))


def _state(function, clause, mention, conditional_span=None):
    if conditional_span is not None or CONDITIONAL.search(clause):
        return "CONDITIONAL", "CONDITIONAL_CLAUSE"
    if UNKNOWN.search(clause):
        return "UNKNOWN", "EXPLICIT_UNKNOWN_CLAUSE"
    left, right = max(0, mention.start() - 28), min(len(clause), mention.end() + 42)
    # A state token never crosses a separately named function.
    for other in FUNCTIONS:
        if other == function:
            continue
        for token in re.finditer(ALIASES[other], clause, re.I):
            if token.end() <= mention.start():
                left = max(left, token.end())
            if token.start() >= mention.end():
                right = min(right, token.start())
    window = clause[left:right]
    negative = bool(NOT_DONE.search(window))
    done = bool(DONE.search(NOT_DONE.sub("", window))) if negative else bool(DONE.search(window))
    if negative and done:
        return "CONFLICTING", "CONFLICTING_STATE_CLAUSE"
    if negative:
        return "EXPLICITLY_NOT_DONE", "EXPLICIT_NEGATED_COMPLETION"
    if done and not EXCLUDED.search(window):
        return "EXPLICITLY_DONE", "EXPLICIT_COMPLETION"
    if (function == PRE_CLEARING_INITIAL_LABEL_QC
            and re.search(QC_COMPLETION_PATTERN, window, re.I)
            and not EXCLUDED.search(window) and not REQUEST.search(clause)):
        return "EXPLICITLY_DONE", "PROVISIONAL_INDEPENDENT_LABEL_BACKGROUND_QC_COMPLETION"
    if function == INITIAL_FIXATION and (
            re.search(r"(?<!未)(?<!经)固定(?:的)?(?:小鼠|鼠|组织|样本)", clause)
            or re.search(r"(?<!un)\bfixed (?:mouse |murine )?(?:tissue|samples?)\b", clause, re.I)):
        if not NOT_DONE.search(clause) and not re.search(r"\bnot\b", clause, re.I):
            return "EXPLICITLY_DONE", "PROVISIONAL_FIXED_SAMPLE_MODIFIER"
    return "UNKNOWN", "MENTION_WITHOUT_EXPLICIT_STATE"


def _merge(records, goal=False):
    states = {item["state"] for item in records}
    positive = "EXPLICITLY_REQUIRED" if goal else "EXPLICITLY_DONE"
    negative = "EXPLICITLY_NOT_REQUIRED" if goal else "EXPLICITLY_NOT_DONE"
    if "CONFLICTING" in states or {positive, negative} <= states:
        return "CONFLICTING"
    if "CONDITIONAL" in states:
        return "CONDITIONAL"
    definite = states & {positive, negative}
    return next(iter(definite)) if definite else "UNKNOWN"


def _qc_anaphora(text, start, end):
    """Bind only one explicitly named QC antecedent within the original sentence.

    A semicolon may separate the request from its antecedent. Contrast,
    conditional, unknown or excluded scope never proves that reference.
    """
    references = list(re.finditer(r"\u5176(?:\u8d28\u63a7|QC)|\b(?:its|their) (?:QC|quality control)\b",
                                  text[start:end], re.I))
    if not references:
        return [], {}
    stops = list(re.finditer(r"[\u3002.\n]", text[:start]))
    sentence_start = stops[-1].end() if stops else 0
    prefix = text[sentence_start:start]
    antecedents = list(re.finditer(ALIASES[PRE_CLEARING_INITIAL_LABEL_QC], prefix, re.I))
    if not antecedents:
        return [], {}
    spans, antecedent_conditions = [], []
    for mention in antecedents:
        for left, right, _, condition in _segments(prefix):
            if left <= mention.start() < mention.end() <= right:
                spans.append(_span(text, sentence_start + left, sentence_start + right))
                antecedent_conditions.append(condition)
                break
    # A contrast before the QC antecedent does not interrupt its own request.
    scope_start = spans[0]["start"] if len(spans) == 1 else sentence_start
    scope = text[scope_start:end]
    blocked = (len(antecedents) != 1 or len(spans) != 1
               or any(condition is not None for condition in antecedent_conditions)
               or re.search(r"\u4f46|\u7136\u800c|\bbut\b|\bhowever\b", scope, re.I)
               or CONDITIONAL.search(scope) or UNKNOWN.search(scope) or EXCLUDED.search(scope))
    if not blocked:
        span = spans[0]
        local = re.search(ALIASES[PRE_CLEARING_INITIAL_LABEL_QC], span["quote"], re.I)
        state, _ = _state(PRE_CLEARING_INITIAL_LABEL_QC, span["quote"], local)
        full_state_conflict = (NOT_DONE.search(span["quote"])
                               and DONE.search(NOT_DONE.sub("", span["quote"])))
        blocked = state in {"CONDITIONAL", "CONFLICTING"} or bool(full_state_conflict)
    audit = dict(reference_status="UNRESOLVED" if blocked else "PROVEN_SINGLE_EXPLICIT_QC_ANTECEDENT",
                 reference_rule="PROVISIONAL_SAME_SENTENCE_UNIQUE_INDEPENDENT_QC_REFERENCE")
    if len(spans) == 1:
        audit["antecedent_span"] = spans[0]
    else:
        audit["antecedent_spans"] = spans
    return references, audit


def _audit(function, text):
    records, instructions = [], []
    goal = function == LYMPHOCYTE_T_B_DISCRIMINATION
    for start, end, sentence, conditional_span in _segments(text):
        clause = text[start:end]
        mentions = _mentions(function, clause, sentence)
        reference = {}
        if function == PRE_CLEARING_INITIAL_LABEL_QC:
            anaphors, reference = _qc_anaphora(text, start, end)
            mentions += anaphors
        if not mentions:
            continue
        span = _span(text, start, end)
        condition = ({"condition_span": deepcopy(conditional_span)}
                     if conditional_span is not None else {})
        condition.update(reference)
        if goal:
            if conditional_span is not None or CONDITIONAL.search(clause):
                state = "CONDITIONAL"
            elif DISCRIMINATE.search(clause) and GOAL_NEGATIVE.search(clause):
                state = "EXPLICITLY_NOT_REQUIRED"
            elif DISCRIMINATE.search(clause) and GOAL_REQUEST.search(clause):
                state = "EXPLICITLY_REQUIRED"
            else:
                state = "UNKNOWN"
            records.append(dict(state=state, rule="PROVISIONAL_EXPLICIT_T_B_GOAL", span=span, **condition))
            continue
        for mention in mentions:
            state, rule = _state(function, clause, mention, conditional_span)
            record = dict(state=state, rule=rule, span=span, **condition)
            if record not in records:
                records.append(record)
        # NOT_DONE alone never authorizes execution in this plan.
        if REQUEST.search(clause) and ACTION.search(clause):
            obligation = ("UNRESOLVED" if reference.get("reference_status") == "UNRESOLVED" else
                          "CONDITIONAL" if conditional_span is not None or CONDITIONAL.search(clause) else
                          "OUTSIDE_OR_NEGATED" if EXCLUDED.search(clause) else "REQUIRED")
            instructions.append(dict(obligation=obligation, span=span, rule="PROVISIONAL_EXPLICIT_CURRENT_PLAN_INSTRUCTION", **condition))
        elif reference.get("reference_status") == "UNRESOLVED":
            instructions.append(dict(obligation="UNRESOLVED", span=span, rule="PROVISIONAL_QC_REFERENCE_SCOPE_REVIEW", **condition))
        elif EXCLUDED.search(clause):
            instructions.append(dict(obligation="OUTSIDE_OR_NEGATED", span=span, rule="PROVISIONAL_EXPLICIT_SCOPE_EXCLUSION"))
    state = _merge(records, goal)
    if goal:
        obligation = {"EXPLICITLY_REQUIRED": "REQUIRED", "EXPLICITLY_NOT_REQUIRED": "NOT_REQUIRED"}.get(state, "UNRESOLVED")
    else:
        values = {item["obligation"] for item in instructions}
        if state in {"CONDITIONAL", "CONFLICTING"} or values & {"CONDITIONAL", "UNRESOLVED"} or {"REQUIRED", "OUTSIDE_OR_NEGATED"} <= values:
            obligation = "UNRESOLVED"
        elif "REQUIRED" in values:
            obligation = "UNRESOLVED" if state == "EXPLICITLY_DONE" else "REQUIRED"
        elif state == "EXPLICITLY_DONE" or "OUTSIDE_OR_NEGATED" in values:
            obligation = "NOT_REQUIRED"
        else:
            obligation = "UNRESOLVED"
    spans = []
    for item in records + instructions:
        if item["span"] not in spans:
            spans.append(item["span"])
        for reference_key in ("condition_span", "antecedent_span"):
            if item.get(reference_key) is not None and item[reference_key] not in spans:
                spans.append(item[reference_key])
    return dict(function=function, state=state, mention_status="MENTIONED" if records else "NOT_MENTIONED",
                execution_obligation=obligation,
                applicability_status="APPLICABLE" if obligation == "REQUIRED" else "NOT_REQUIRED_FOR_EXECUTION" if obligation == "NOT_REQUIRED" else "UNRESOLVED",
                review_required=bool(records) and obligation == "UNRESOLVED",
                state_assertions=records, execution_instructions=instructions, question_spans=spans,
                provisional=True, scientific_truth=None, completion_does_not_imply_must_skip=True)


def propose_task_state(question, *, evidence_ids=()):
    """Propose four finite functions from unchanged task text, with exact spans.

    Optional task_initial_states metadata only detects conflicts; it cannot
    authorize execution or establish goals. Unmentioned functions emit no req.
    Explicit completion instructions can require actions whose initial state
    is unspecified; this does not claim the starting state is NOT_DONE.
    """
    if not isinstance(question, dict):
        raise ValueError("Question must be a mapping")
    text = question.get("question", question.get("text", ""))
    if not isinstance(text, str):
        raise ValueError("Question text must be a string")
    evidence_ids = list(evidence_ids)
    if any(not isinstance(item, str) for item in evidence_ids):
        raise ValueError("Evidence IDs must be strings")
    question_sha256 = digest(question)
    question_text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    audits = {function: _audit(function, text) for function in FUNCTIONS}
    for audit in audits.values():
        audit.update(question_sha256=question_sha256, question_text_sha256=question_text_sha256)
    metadata = question.get("task_initial_states", {})
    if not isinstance(metadata, dict):
        raise ValueError("task_initial_states must be a mapping")
    for function, audit in audits.items():
        if function not in metadata:
            continue
        supplied = metadata[function]
        audit.update(metadata_state=deepcopy(supplied), metadata_pointer="/task_initial_states/" + function)
        if audit["mention_status"] == "NOT_MENTIONED":
            continue
        allowed = {"EXPLICITLY_DONE", "EXPLICITLY_NOT_DONE", "UNKNOWN", "CONDITIONAL"}
        if not isinstance(supplied, str) or supplied not in allowed or (supplied != audit["state"] and supplied != "UNKNOWN"):
            audit.update(state="CONFLICTING", execution_obligation="UNRESOLVED",
                         applicability_status="UNRESOLVED", review_required=True, metadata_conflict=True)
    requirements = []
    for function, audit in audits.items():
        if audit["mention_status"] == "NOT_MENTIONED":
            continue
        goal = function == LYMPHOCYTE_T_B_DISCRIMINATION
        obligation = audit["execution_obligation"]
        if goal:
            wording = ("Support the explicitly requested T/B cell discrimination function with applicable scientific evidence; marker-name occurrence does not establish validity."
                       if obligation == "REQUIRED" else
                       "Review applicability of T/B cell discrimination against the original task; preserve unresolved or explicitly excluded goal scope.")
        elif obligation == "REQUIRED":
            wording = "Include the explicitly requested " + function + " action within this plan's stated timing/dependency scope; this checks declarations, not scientific success."
        elif obligation == "NOT_REQUIRED":
            wording = "Record the task's completed/excluded " + function + " state without converting it into a necessary execution or a blanket prohibition on repeating it."
        else:
            wording = "Review applicability and execution scope of " + function + "; unresolved starting state does not authorize treating its omission as satisfied."
        requirements.append(dict(id="TASK_INITIAL_FUNCTION_" + function,
                                 kind="SCIENTIFIC" if goal else "COMPLETENESS",
                                 necessary=obligation != "NOT_REQUIRED",
                                 evidence_ids=list(evidence_ids) if goal else [],
                                 text=wording, function=function,
                                 question_spans=deepcopy(audit["question_spans"]),
                                 necessity_status=obligation, applicability_status=audit["applicability_status"],
                                 applicability={},
                                 review_required=audit["review_required"],
                                 origin="PROVISIONAL_TASK_FUNCTION_NOT_SCIENTIFIC_GOLD",
                                 literal_rule=dict(type="TASK_INITIAL_FUNCTION", function=function, state_audit=deepcopy(audit))))
    if requirements:
        validate_requirements(requirements)
    return dict(schema_version=VERSION, question_sha256=question_sha256,
                question_text_sha256=question_text_sha256,
                hash_format="canonical-json-sha256-v1", functions=audits, requirements=requirements,
                provisional=True, rule_scope="FINITE_NATURAL_LANGUAGE_PROPOSALS_PENDING_REVIEW",
                scientific_gold=None,
                legacy_completed_label_scope_warning="A completed diffusion/label statement does not prove independent initial label QC completed; do not propagate mixed NO_REPEAT_LABEL_QC into QC.",
                no_repeat_policy="Existing explicit NO_REPEAT constraints remain separate; done alone does not establish must-skip.")
