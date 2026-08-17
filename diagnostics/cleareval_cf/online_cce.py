"""ClearEval counterfactual-validity overlay -- online CCE scoring (Task 3).

This module is the ``--online`` implementation behind
``run_original_cce.CCEScorer.score_online``.  It is deliberately isolated in
its own file and lazily imported so that importing/building the test suite never
touches the repo's model stack (``models.Model_Loader``, API SDKs, config.yaml).

THE ONLINE PATH MUST NEVER RUN INSIDE THE TEST SUITE -- tests are offline by
contract (Global constraint: no network in any test).

What it does (mirrors the production evaluation flow in
``OEQ_run_grading_new.py``):
1. Load the repo's model loader from ``config/config.yaml`` and instantiate the
   teacher (default ``openai_gpt-5.2-thinking``).
2. Ask the teacher for the per-question user-preference vector
   (``USER_PREFERENCE_PROMPT``) -- used by S_method.
3. Build the completeness/correctness/extraction prompt exactly as the
   production ``evaluate_response_with_teacher`` does from
   ``prompts/eval_oeq_teacher_rubric.txt`` (same placeholders + the same
   [CRITICAL FORMAT RULE] enforcement) and call the teacher.
4. Parse the JSON, take ``scores.completeness`` / ``scores.correctness`` and
   ``extraction`` (method_name, marker_dict, clearing_total_time_hours...),
   then compute Effectiveness with the *production-equivalent* rule stack --
   the teacher-supplied extraction feeds the re-implemented
   ``calculate_effectiveness_score`` (see the adapter docstring's REUSE vs
   RE-IMPLEMENTATION note).

Metadata: teacher model name, production rubric prompt path + sha256, schema and
operator versions, timestamp, and the input text's sha256 are recorded on every
call.

Standing failure behavior mirrors the production path: an empty/parse-failed
teacher response returns an explicit ``status`` failure record (never a
fabricated score).  The test suite never imports this module.
"""

from __future__ import annotations

import json
import os
import re
import sys
import traceback
from typing import Any, Dict, Optional, Tuple

_PG_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_PG_DIR))
_QAR_SRC = os.path.join(_REPO_ROOT, "dataset", "Q+AR", "src")

try:  # package context
    from .run_original_cce import (
        calculate_effectiveness_score,
        make_metadata,
        prompt_meta,
        sha256_text,
    )
    from .run_original_cce import RuleKBs
except ImportError:  # script context
    _PG_DIR = os.path.dirname(os.path.abspath(__file__))
    if _PG_DIR not in sys.path:
        sys.path.insert(0, _PG_DIR)
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    from run_original_cce import (  # type: ignore
        RuleKBs,
        calculate_effectiveness_score,
        make_metadata,
        prompt_meta,
        sha256_text,
    )


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


_PREF_PROMPT_PATH = os.path.join(_REPO_ROOT, "prompts", "parse_user_preference_vector.py")
_RUBRIC_PATH = os.path.join(_REPO_ROOT, "prompts", "eval_oeq_teacher_rubric.txt")
_CONFIG_PATH = os.path.join(_REPO_ROOT, "config", "config.yaml")


def _load_pref_prompt() -> str:
    with open(_PREF_PROMPT_PATH, "r", encoding="utf-8") as fh:
        src = fh.read()
    # USER_PREFERENCE_PROMPT is a Python string constant in a .py file; import it
    # rather than parse source text.
    import importlib.util

    spec = importlib.util.spec_from_file_location("parse_user_preference_vector", _PREF_PROMPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return getattr(mod, "USER_PREFERENCE_PROMPT")


def _model_instance(teacher_name: str, config_path: Optional[str]) -> Any:
    from models.Model_Loader import ModelLoader  # lazy; online only

    loader = ModelLoader(config_path or _CONFIG_PATH)
    models = loader.load_models()
    if teacher_name not in models:
        raise RuntimeError(f"teacher {teacher_name!r} not in config models: {sorted(models)}")
    return models[teacher_name]


def _strip_fences(text: str) -> str:
    s = text.strip()
    m = re.match(r"^[`~]{3}\s*[jJ][sS][oO][nN]?\s*\n?", s)
    if m:
        s = s[m.end():]
    s = re.sub(r"\n?[`~]{3}\s*$", "", s)
    return s.strip()


def _sanitize_unicode_escapes(s: str) -> str:
    def _fix(m: "re.Match[str]") -> str:
        seq = m.group(1)
        if len(seq) == 4 and all(c in "0123456789abcdefABCDEF" for c in seq):
            return m.group(0)
        return "\ufffd"
    return re.sub(r"\\u([0-9a-fA-F]{0,4})", _fix, s)


def _extract_question_meta(kbs: RuleKBs, question_id: int) -> Dict[str, Any]:
    return kbs.question_meta(question_id)


def score_online_cce(
    protocol_text: str,
    question_id: int,
    teacher_name: str = "openai_gpt-5.2-thinking",
    config_path: Optional[str] = None,
    repo_root: str = _REPO_ROOT,
) -> Dict[str, Any]:
    """Score one protocol through the production teacher path (online)."""
    kbs = RuleKBs(repo_root)
    qm = _extract_question_meta(kbs, question_id)
    meta = make_metadata(mode="online", teacher_model=teacher_name)
    input_hash = sha256_text(protocol_text)
    meta["input_sha256"] = input_hash
    meta.update(prompt_meta())

    teacher = _model_instance(teacher_name, config_path)
    try:
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            # 1) user preference vector (production get_user_preference_vector)
            pref_prompt = _load_pref_prompt().replace("{user_text}", qm.get("question_text", "") or "")
            user_pref_vector: Dict[str, Any] = {}
            try:
                resp = loop.run_until_complete(teacher._acall(pref_prompt))
                content = (resp or {}).get("content", "") or ""
                content = _strip_fences(content)
                if content:
                    data = json.loads(content)
                    user_pref_vector = data.get("user_input_vectors", {})
            except Exception:
                user_pref_vector = {}
            if not user_pref_vector:
                # deterministic fallback (documented divergence 2)
                user_pref_vector = kbs.demand_vectors.get(str(int(question_id)), {})

            # 2) building the production eval prompt
            try:
                with open(_RUBRIC_PATH, "r", encoding="utf-8") as fh:
                    rubric = fh.read()
            except OSError as exc:
                return _fail(meta, f"rubric load failed: {exc}")
            method_name = "Unknown"
            m = re.search(r'(?:\*\*)?Chosen Method:\*?\s*([^\n]+)', protocol_text, re.IGNORECASE)
            if m:
                method_name = m.group(1).strip()
            sample_size = ""
            size_match = re.search(
                r'\d+\s*mm\s*[×xX]\s*\d+\s*mm\s*[×xX]\s*\d+\s*mm|\d+[-–~]\d+\s*mm|\d+\s*μm|\d+\s*cm',
                qm.get("question_text", "") or "",
            )
            if size_match:
                sample_size = size_match.group(0)
            # [CRITICAL FORMAT RULE] block copied VERBATIM from production
            # OEQ_run_grading_new.py:evaluate_response_with_teacher (final-review finding #5).
            format_enforcement = (
                "\n[CRITICAL FORMAT RULE]\n"
                "Your ENTIRE response must be a SINGLE valid JSON object. "
                "Use the EXACT nested structure shown in the final example below. "
                "Do NOT output separate JSON blocks for each section. "
                "Do NOT put keys like C_step, Co_order, or marker_dict at the top level. "
                "They MUST be nested inside 'scores.completeness', 'scores.correctness', and 'extraction'.\n\n"
            )
            prompt = (
                rubric
                .replace("{{question_text}}", qm.get("question_text", "") or "")
                .replace("{{model_generated_protocol}}", protocol_text)
                .replace("{{method_name}}", method_name)
                .replace("{{sample_size}}", sample_size)
            )
            prompt = prompt.replace(
                "1. 完整性评估 Prompt (Completeness)",
                format_enforcement + "1. 完整性评估 Prompt (Completeness)")

            resp = loop.run_until_complete(teacher._acall(prompt))
            content = (resp or {}).get("content", "") or ""
            if not content:
                return _fail(meta, "teacher returned empty content")
            llm_output = json.loads(_sanitize_unicode_escapes(_strip_fences(content)))

            scores_block = llm_output.get("scores", {})
            extraction = llm_output.get("extraction", {})
            if not scores_block:
                return _fail(meta, "teacher output missing 'scores' object")
            if not isinstance(extraction, dict):
                extraction = {}
            completeness = scores_block.get("completeness", {})
            correctness = scores_block.get("correctness", {})
            judge_payload = {"completeness": completeness, "correctness": correctness}

            # effectiveness via teacher-supplied extraction + rule stack
            extraction = _coerce_extraction(extraction)
            quantitative_data = {
                "method_name": extraction.get("method_name") or "",
                "total_time_hours": _to_float(extraction.get("clearing_total_time_hours"), 0.0),
                "sample_tier": qm.get("tissue_tier_code", ""),
                "tissue_ri_value": qm.get("tissue_ri_value", 0.0),
            }
            marker_dict = extraction.get("marker_dict") or {}
            if not isinstance(marker_dict, dict):
                marker_dict = {}
            eff = calculate_effectiveness_score(
                quantitative_data=quantitative_data,
                user_pref_vector_dict=user_pref_vector,
                marker_dict=marker_dict,
                marker_query_targets=qm.get("marker_query_targets", []),
                kbs=kbs,
            )
            eff["_source"] = "online_production_path"

            # assemble the canonical CCE record (mirrors assemble_cce)
            from .run_original_cce import assemble_cce  # same package

            return assemble_cce(question_id, protocol_text, judge_payload, eff, meta, status="ok")
        finally:
            loop.close()
            asyncio.set_event_loop(None)
    except Exception as exc:  # noqa: BLE001 -- report, never fabricate
        meta["error_type"] = type(exc).__name__
        return _fail(meta, f"{exc}\n{traceback.format_exc(limit=5)}")


def _coerce_extraction(extraction: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    out["method_name"] = str(extraction.get("method_name", "") or "").strip()
    out["clearing_total_time_hours"] = extraction.get("clearing_total_time_hours")
    out["marker_dict"] = extraction.get("marker_dict", {})
    return out


def _to_float(val: Any, default: float) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _fail(meta: Dict[str, Any], error: str) -> Dict[str, Any]:
    return {
        "status": "judge_failed",
        "error": error,
        "metadata": meta,
        "total_cc": None,
        "components": None,
    }


def main() -> int:  # pragma: no cover - manual CLI/online
    print("online_cce is an internal module used by run_original_cce --online; run that instead.")
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
