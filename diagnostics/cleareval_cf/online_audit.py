"""ClearEval counterfactual-validity overlay -- online DiagnosticAudit judge
(Task 3).  Lazily imported by ``run_diagnostic_audit.OnlineAuditJudge`` for the
``--online`` mode; NEVER imported by the test suite (offline by contract).

Builds the role-blind prompt from ``prompts/diagnostic_audit_v1.txt`` (question
+ ONE protocol), calls the repo's teacher model, parses the strict JSON into a
``schemas.DiagnosticAuditResult``, and returns a status-tagged result.  Failure
(empty/parse error) returns an explicit failure record -- never a fabricated
finding.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict, Optional

_PG_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_PG_DIR))

try:  # package context
    from .schemas import DiagnosticAuditResult, ValidationError
except ImportError:
    sys.path.insert(0, _PG_DIR)
    if _REPO_ROOT not in sys.path:
        sys.path.insert(0, _REPO_ROOT)
    from schemas import DiagnosticAuditResult, ValidationError  # type: ignore

PROMPT_PATH = os.path.join(_PG_DIR, "prompts", "diagnostic_audit_v1.txt")
_CONFIG_PATH = os.path.join(_REPO_ROOT, "config", "config.yaml")


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


def online_audit_call(
    question_text: str,
    protocol_text: str,
    teacher_name: str,
    config_path: Optional[str],
    repo_root: str,
) -> Dict[str, Any]:
    """One online role-blind DiagnosticAudit call."""
    from .run_diagnostic_audit import build_audit_prompt, sha256_text  # same package

    prompt = build_audit_prompt(question_text, protocol_text)
    teacher = _model_instance(teacher_name, config_path)
    try:
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            resp = loop.run_until_complete(teacher._acall(prompt))
            content = (resp or {}).get("content", "") or ""
            if not content:
                return {"status": "judge_failed",
                        "error": "teacher returned empty content",
                        "input_sha256": sha256_text(protocol_text)}
            data = json.loads(_strip_fences(content))
            finding = DiagnosticAuditResult.from_dict(data)
            return {"status": "ok", "finding": finding,
                    "input_sha256": sha256_text(protocol_text)}
        finally:
            loop.close()
            asyncio.set_event_loop(None)
    except (ValidationError, json.JSONDecodeError) as exc:
        return {"status": "parse_failed", "error": f"{type(exc).__name__}: {exc}",
                "input_sha256": sha256_text(protocol_text)}
    except Exception as exc:  # noqa: BLE001 -- report, never fabricate
        return {"status": "judge_failed", "error": f"{type(exc).__name__}: {exc}",
                "input_sha256": sha256_text(protocol_text)}


def main() -> int:  # pragma: no cover - internal/online module
    print("online_audit is an internal module used by run_diagnostic_audit --online.")
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
