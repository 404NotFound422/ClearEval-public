"""ClearEval counterfactual-validity overlay -- seed selection + split (Task 1).

Selects exactly 24 seed candidates (question x model pairs from the
frozen 1-shot OEQ run) -- 8 per scenario stratum -- and splits them
16 development / 8 blind at the *seed* level (never at the mutation
level).  Everything is deterministic (byte-identical across runs) and
offline; no network, no third-party packages.

No gold / expert / mutation labels or scorer thresholds are used to
select content.  The only filters applied are the mechanical
eligibility pre-filters documented below.

--------------------------------------------------------------------------------
Derivation rules (all mechanical, all documented in DATA_SUMMARY.md)
--------------------------------------------------------------------------------

1. scenario_type (per question, from question text / marker panel):
     ERROR_CORRECTION  if question text matches
                       r"错误|纠正|纠错|排查|失败|修正|不妥|不当|问题所在"
     COMPLEX_GENERATION if not ERROR_CORRECTION and
                       len(marker_query_targets) >= 4
     SIMPLE_GENERATION otherwise
   (Counts on the frozen corpus -- recomputed at report time from
   question_final.json via derive_scenario_type, never hardcoded: 60 / 70 / 123.)

2. clearing_method_family (per question, from question text only):
     first match wins, in this priority order (all ASCII patterns are
     case-insensitive; \\b only around pure-ASCII tokens):
       CUBIC -> "CUBIC"; PEGASOS -> "PEGASOS"; iDISCO -> "iDISCO";
       FDISCO -> "FDISCO"; uDISCO -> "uDISCO"; 3DISCO -> "3DISCO";
       DISCO -> "DISCO"; \\bMACS\\b -> "MACS"; \\beFLASH\\b -> "eFLASH";
       CLARITY -> "CLARITY"; SHANEL -> "SHANEL"; \\bSeeDB\\b -> "SeeDB";
       ScaleS -> "Scale"; \\bScale\\b -> "Scale"; \\bSWITCH\\b -> "SWITCH";
       甲醇 -> "SOLVENT_BASED"; 有机溶剂 -> "SOLVENT_BASED";
       otherwise -> "UNKNOWN".

3. labeling_requirement (per question, from question text + marker panel):
     tg_text  = text contains any of
                转基因|荧光蛋白|报告基因|遗传标记|外源基因|GFP|YFP|Thy1|
                tdTomato|Ai14|Cre|AAV
     im_text  = text contains any of 抗体|免疫
     tg_marker = any marker_name matches
                 r"GFP|YFP|Thy1|tdTomato|Ai14|reporter|Cre" (re.I)
     Rule:
       if (tg_text or tg_marker) and (im_text or n_targets >= 4):
           MIXED            # transgenic signal combined with an
                            # immuno mention or a >=4-marker panel
       elif (tg_text or tg_marker):  TRANSGENIC
       elif im_text:                 IMMUNOLABELING
       else:                         UNKNOWN
     n_targets participates only as the panel-size upgrade condition
     above; it never downgrades a text-derived class.

4. Eligibility pre-filter (mechanical; nothing semantic):
     a. response record exists for (model, question_id);
     b. response_text non-empty after strip;
     c. evaluation record exists;
     d. usable totals present for completeness AND correctness AND
        effectiveness, where a part's usable total is
        total_weighted_score if numeric, else
        total_completeness_score / total_correctness_score if numeric
        (a few frozen records use the *_score variant field name);
     e. correctness.critical_warnings empty or absent
        (missing key / None / empty list pass; anything truthy rejects).
   Rejected pairs are counted by reason for DATA_SUMMARY.md.

5. CCE score = completeness.total + correctness.total + effectiveness.total.
   cce_bucket = equal-width third of the *observed eligible-pool range*
   [min, max]: LOW  if v < min + (max-min)/3,
               MID  if v < min + 2*(max-min)/3,
               HIGH otherwise.

6. Selection (per stratum, greedy round-robin, RNG-free):
     candidates sorted by (question_id, source_model);
     for round r in 0..7, the leading dimension is
     DIMENSIONS[r % 5] where DIMENSIONS = (sample_tier, source_model,
     clearing_method_family, labeling_requirement, cce_bucket);
     pick the unselected candidate minimizing the lexicographic key
       (count[lead_dim][value],
        sum over other dims of count[dim][value],
        question_id, source_model)
     i.e. each round fills the least-represented value of the rotating
     lead dimension, with total representation as tie-break and
     (question_id, source_model) as the final tie-break.  This
     maximizes stratum-internal diversity over the five dimensions.

7. seed_id assignment: the 24 selected candidates are sorted by
   (scenario_type rank SIMPLE < COMPLEX < ERROR, question_id,
   source_model) and receive SEED-001..SEED-024 in that order, so ids
   are stable and strata are contiguous in the manifest.

8. Split (seeds only; the ONLY user of the seeded RNG):
     rng = random.Random(split_seed)
     stratum order = rng.sample(STRATA, 3); the first two drawn strata
     get 6 development seeds each, the third gets 4 (documented in
     DATA_SUMMARY.md); within a stratum the blind seeds are
     rng.sample(sorted(seed_ids), n_blind) and everything else is
     development.  Development = 16, blind = 8, disjoint by
     construction and re-checked by SplitManifest.validate().

--------------------------------------------------------------------------------
Split guard (hard requirement)
--------------------------------------------------------------------------------

load_split_manifest(path=None, role=None) and
assert_split_access(path_or_seed, role, manifest=None): code running in
role="development" that tries to open a blind-listed seed id -- or any
file path whose basename contains a blind-listed SEED-<NNN> token --
gets BlindSplitAccessError.  The guard is one-directional by design:
role="blind" is allowed to open anything, because blind-role code may
run both before and after unblinding.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import random
import re
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:  # run as `python -m diagnostics.cleareval_cf.seed_selector`
    from .schemas import (
        BlindSplitAccessError,
        ScenarioType,
        SeedCandidate,
        SplitManifest,
        load_seed_candidates,
        write_seed_candidates,
    )
except ImportError:  # run as `python diagnostics/cleareval_cf/seed_selector.py`
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from schemas import (  # type: ignore
        BlindSplitAccessError,
        ScenarioType,
        SeedCandidate,
        SplitManifest,
        load_seed_candidates,
        write_seed_candidates,
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(PKG_DIR))

ALGORITHM_VERSION = "seed-selector-v1"
DEFAULT_SPLIT_SEED = 20260817
N_SEEDS_PER_STRATUM = 8
N_TOTAL_SEEDS = 24
N_DEV = 16
N_BLIND = 8

# The 13 frozen 1-shot base models (sorted; matches file inventory).
MODEL_NAMES = sorted(
    [
        "gemini-3-flash",
        "gemini-3-pro",
        "glm4.7-thinking",
        "glm4.7-unthinking",
        "openai_claude-sonnet-4.6",
        "openai_deepseek-chat",
        "openai_deepseek-reasoner",
        "openai_gpt-5.2-fast",
        "openai_gpt-5.2-thinking",
        "openai_qwen3-14b",
        "openai_qwen3-235b",
        "openai_qwen3-32b",
        "openai_qwen3-max",
    ]
)

STRATUM_ORDER = [
    ScenarioType.SIMPLE_GENERATION,
    ScenarioType.COMPLEX_GENERATION,
    ScenarioType.ERROR_CORRECTION,
]

# Question mode: the audit established that all 253 OEQ questions are
# single-format application/protocol-design prompts with no explicit
# mode field, so question_mode is this constant for every seed.
QUESTION_MODE = "APPLICATION_PROTOCOL_DESIGN"

# Stratification dimensions used by the greedy round-robin.
DIMENSIONS = [
    "sample_tier",
    "source_model",
    "clearing_method_family",
    "labeling_requirement",
    "cce_bucket",
]

ERROR_SCENARIO_RE = re.compile(r"错误|纠正|纠错|排查|失败|修正|不妥|不当|问题所在")

# (regex, family) -- first match wins; ASCII patterns are case-insensitive.
METHOD_FAMILY_KEYWORDS: List[Any] = [
    (re.compile(r"CUBIC", re.I), "CUBIC"),
    (re.compile(r"PEGASOS", re.I), "PEGASOS"),
    (re.compile(r"iDISCO", re.I), "iDISCO"),
    (re.compile(r"FDISCO", re.I), "FDISCO"),
    (re.compile(r"uDISCO", re.I), "uDISCO"),
    (re.compile(r"3DISCO", re.I), "3DISCO"),
    (re.compile(r"DISCO", re.I), "DISCO"),
    (re.compile(r"\bMACS\b", re.I), "MACS"),
    (re.compile(r"\beFLASH\b", re.I), "eFLASH"),
    (re.compile(r"CLARITY", re.I), "CLARITY"),
    (re.compile(r"SHANEL", re.I), "SHANEL"),
    (re.compile(r"\bSeeDB\b", re.I), "SeeDB"),
    (re.compile(r"ScaleS", re.I), "Scale"),
    (re.compile(r"\bScale\b", re.I), "Scale"),
    (re.compile(r"\bSWITCH\b", re.I), "SWITCH"),
    (re.compile(r"甲醇"), "SOLVENT_BASED"),
    (re.compile(r"有机溶剂"), "SOLVENT_BASED"),
]

TRANSGENIC_TEXT_KEYWORDS = [
    "转基因",
    "荧光蛋白",
    "报告基因",
    "遗传标记",
    "外源基因",
    "GFP",
    "YFP",
    "Thy1",
    "tdTomato",
    "Ai14",
    "Cre",
    "AAV",
]
IMMUNO_TEXT_KEYWORDS = ["抗体", "免疫"]
TRANSGENIC_MARKER_RE = re.compile(r"GFP|YFP|Thy1|tdTomato|Ai14|reporter|Cre", re.I)

_SEED_TOKEN_RE = re.compile(r"SEED-\d{3}")

QUESTION_FILE_REL = os.path.join("dataset", "Q+AR", "src", "question_final.json")
RESPONSE_DIR_REL = os.path.join("dataset", "Q+AR", "model_response")
EVAL_DIR_REL = os.path.join("dataset", "Q+AR", "result")

DEFAULT_MANIFEST_PATH = os.path.join(PKG_DIR, "manifests", "split_manifest.json")
DEFAULT_SEED_PATH = os.path.join(PKG_DIR, "manifests", "seed_candidates.jsonl")
DEFAULT_DEV_SEED_PATH = os.path.join(PKG_DIR, "manifests", "seed_candidates_development.jsonl")


# ---------------------------------------------------------------------------
# Mechanical derivations
# ---------------------------------------------------------------------------


def derive_scenario_type(question_text: str, n_marker_targets: int) -> ScenarioType:
    if ERROR_SCENARIO_RE.search(question_text):
        return ScenarioType.ERROR_CORRECTION
    if n_marker_targets >= 4:
        return ScenarioType.COMPLEX_GENERATION
    return ScenarioType.SIMPLE_GENERATION


def derive_method_family(question_text: str) -> str:
    for pattern, family in METHOD_FAMILY_KEYWORDS:
        if pattern.search(question_text):
            return family
    return "UNKNOWN"


def derive_labeling_requirement(
    question_text: str, marker_names: List[str], n_marker_targets: int
) -> str:
    tg_text = any(kw in question_text for kw in TRANSGENIC_TEXT_KEYWORDS)
    im_text = any(kw in question_text for kw in IMMUNO_TEXT_KEYWORDS)
    tg_marker = any(TRANSGENIC_MARKER_RE.search(name) for name in marker_names)
    if tg_text or tg_marker:
        if im_text or n_marker_targets >= 4:
            return "MIXED"
        return "TRANSGENIC"
    if im_text:
        return "IMMUNOLABELING"
    return "UNKNOWN"


def _part_total(part: Any) -> Optional[float]:
    """Usable total for one scores part (see eligibility rule d)."""
    if not isinstance(part, dict):
        return None
    t = part.get("total_weighted_score")
    if isinstance(t, (int, float)) and not isinstance(t, bool):
        return float(t)
    for alt in ("total_completeness_score", "total_correctness_score"):
        t = part.get(alt)
        if isinstance(t, (int, float)) and not isinstance(t, bool):
            return float(t)
    return None


# ---------------------------------------------------------------------------
# Candidate model
# ---------------------------------------------------------------------------


@dataclass
class _Candidate:
    question_id: int
    source_model: str
    source_file: str
    response_text: str
    scenario_type: ScenarioType
    sample_tier: str
    clearing_method_family: str
    labeling_requirement: str
    n_marker_targets: int
    cce_scores: Dict[str, Any]
    cce_total: float
    cce_bucket: str

    def value(self, dim: str) -> Any:
        return getattr(self, dim)


# ---------------------------------------------------------------------------
# Pool building + eligibility
# ---------------------------------------------------------------------------


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def load_questions(data_root: str) -> Dict[int, Dict[str, Any]]:
    with open(os.path.join(data_root, QUESTION_FILE_REL), "r", encoding="utf-8") as fh:
        records = json.load(fh)
    return {r["question_id"]: r for r in records}


def _default_stratum_question_counts() -> Dict[str, int]:
    """Question-level scenario counts derived from question_final.json (253 q)."""
    counts: "collections.Counter[str]" = collections.Counter()
    for r in load_questions(REPO_ROOT).values():
        qtext = r["question"]
        n_targets = len(r.get("marker_query_targets") or [])
        counts[derive_scenario_type(qtext, n_targets).value] += 1
    return {
        sc.value: counts[sc.value]
        for sc in STRATUM_ORDER
    }


def build_pool(data_root: str) -> Dict[str, Any]:
    """Build the eligible candidate pool + rejection tallies.

    Returns dict with 'candidates', 'rejections' (Counter by reason),
    'per_model_eligible', 'per_stratum_pool', 'input_hashes',
    'cc_range' (min, max of eligible cce totals), 'bucket_boundaries'.
    """
    questions = load_questions(data_root)
    rejections: "collections.Counter[str]" = collections.Counter()
    per_model_eligible: "collections.Counter[str]" = collections.Counter()
    per_stratum_pool: "collections.Counter[str]" = collections.Counter()
    candidates: List[_Candidate] = []
    cce_totals: List[float] = []

    input_hashes: Dict[str, str] = {}
    qpath = os.path.join(data_root, QUESTION_FILE_REL)
    input_hashes[qpath] = _sha256_file(qpath)

    for model in MODEL_NAMES:
        resp_path = os.path.join(data_root, RESPONSE_DIR_REL, f"from_{model}_1-shot.json")
        eval_path = os.path.join(data_root, EVAL_DIR_REL, f"evaluation_results_{model}_1-shot.json")
        input_hashes[resp_path] = _sha256_file(resp_path)
        input_hashes[eval_path] = _sha256_file(eval_path)
        with open(resp_path, "r", encoding="utf-8") as fh:
            responses = json.load(fh)
        with open(eval_path, "r", encoding="utf-8") as fh:
            evals = json.load(fh)
        resp_by_qid = {r["question_id"]: r for r in responses}
        eval_by_qid = {r["question_id"]: r for r in evals}

        for qid in sorted(questions):
            if qid not in resp_by_qid:
                rejections["missing_response_record"] += 1
                continue
            resp = resp_by_qid[qid]
            response_text = resp.get("model_response") or ""
            if not response_text.strip():
                rejections["empty_response_text"] += 1
                continue
            if qid not in eval_by_qid:
                rejections["missing_eval_record"] += 1
                continue
            ev = eval_by_qid[qid].get("evaluation") or {}
            scores = ev.get("scores") or {}
            comp = scores.get("completeness")
            corr = scores.get("correctness")
            eff = scores.get("effectiveness")
            totals = [_part_total(p) for p in (comp, corr, eff)]
            if any(t is None for t in totals):
                rejections["missing_cc_score_totals"] += 1
                continue
            cw = (corr or {}).get("critical_warnings")
            if cw:  # absent / None / empty list pass; anything truthy rejects
                rejections["critical_warnings_present"] += 1
                continue

            question = questions[qid]
            qtext = question["question"]
            tier = question["tissue_hierarchy_from_tissue_xlsx"]["tissue_tier_code"]
            targets = question["marker_query_targets"]
            names = [t["marker_name"] for t in targets]
            n_targets = len(targets)
            scenario = derive_scenario_type(qtext, n_targets)
            cce_total = float(sum(t for t in totals if t is not None))
            cce_totals.append(cce_total)
            cce_scores = {
                "completeness": _sub_scores(comp, ("c_step", "c_param")),
                "correctness": _sub_scores(corr, ("co_order", "co_method", "co_param", "co_chem")),
                "effectiveness": _sub_scores(eff, ("s_method", "s_label", "s_trans", "s_time")),
                "total": cce_total,
            }
            candidates.append(
                _Candidate(
                    question_id=qid,
                    source_model=model,
                    source_file=_relpath(resp_path, data_root),
                    response_text=response_text,
                    scenario_type=scenario,
                    sample_tier=tier,
                    clearing_method_family=derive_method_family(qtext),
                    labeling_requirement=derive_labeling_requirement(qtext, names, n_targets),
                    n_marker_targets=n_targets,
                    cce_scores=cce_scores,
                    cce_total=cce_total,
                    cce_bucket="",  # filled after the range is known
                )
            )
            per_model_eligible[model] += 1
            per_stratum_pool[scenario.value] += 1

    # CCE bucket: equal-width thirds of the observed eligible range.
    vals = sorted(cce_totals)
    lo, hi = vals[0], vals[-1]
    span = hi - lo
    t1, t2 = lo + span / 3.0, lo + 2.0 * span / 3.0
    for cand in candidates:
        v = cand.cce_total
        cand.cce_bucket = "LOW" if v < t1 else ("MID" if v < t2 else "HIGH")

    return {
        "candidates": candidates,
        "rejections": rejections,
        "per_model_eligible": per_model_eligible,
        "per_stratum_pool": per_stratum_pool,
        "input_hashes": input_hashes,
        "cc_range": (lo, hi),
        "bucket_boundaries": (t1, t2),
    }


def _sub_scores(part: Dict[str, Any], sub_keys: tuple) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k in sub_keys:
        sub = part.get(k) or {}
        out[k] = {"score": sub.get("score"), "max_score": sub.get("max_score")}
    total = _part_total(part)
    assert total is not None  # eligibility already guaranteed a usable total
    out["total_weighted_score"] = float(total)
    return out


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def select_seeds(pool: Dict[str, Any]) -> List[_Candidate]:
    """Greedy round-robin selection: 8 seeds per stratum (see docstring)."""
    by_stratum: Dict[ScenarioType, List[_Candidate]] = {s: [] for s in STRATUM_ORDER}
    for cand in pool["candidates"]:
        by_stratum[cand.scenario_type].append(cand)

    selected: List[_Candidate] = []
    for stratum in STRATUM_ORDER:
        pool_sorted = sorted(by_stratum[stratum], key=lambda c: (c.question_id, c.source_model))
        counts = {dim: collections.Counter() for dim in DIMENSIONS}
        chosen: List[_Candidate] = []
        chosen_ids = set()
        for round_idx in range(N_SEEDS_PER_STRATUM):
            lead = DIMENSIONS[round_idx % len(DIMENSIONS)]
            best: Optional[_Candidate] = None
            best_key: Optional[tuple] = None
            for cand in pool_sorted:
                if (cand.question_id, cand.source_model) in chosen_ids:
                    continue
                lead_cnt = counts[lead][cand.value(lead)]
                other_sum = sum(
                    counts[d][cand.value(d)] for d in DIMENSIONS if d != lead
                )
                key = (lead_cnt, other_sum, cand.question_id, cand.source_model)
                if best_key is None or key < best_key:
                    best, best_key = cand, key
            assert best is not None
            chosen.append(best)
            chosen_ids.add((best.question_id, best.source_model))
            for dim in DIMENSIONS:
                counts[dim][best.value(dim)] += 1
        selected.extend(chosen)
    return selected


def assign_seed_ids(selected: List[_Candidate]) -> List[_Candidate]:
    """Assign SEED-001..024 sorted by (stratum rank, question_id, model)."""
    rank = {s: i for i, s in enumerate(STRATUM_ORDER)}
    ordered = sorted(
        selected, key=lambda c: (rank[c.scenario_type], c.question_id, c.source_model)
    )
    for idx, cand in enumerate(ordered, start=1):
        cand.seed_id = f"SEED-{idx:03d}"
    return ordered


# ---------------------------------------------------------------------------
# Split (seeds only; the only RNG user)
# ---------------------------------------------------------------------------


def make_split(seeds: List[_Candidate], split_seed: int) -> Dict[str, Any]:
    """Deterministic seed-level split (see docstring rule 8)."""
    rng = random.Random(split_seed)
    strata_drawn = rng.sample(list(STRATUM_ORDER), 3)
    dev_per_stratum = {s: 6 for s in strata_drawn[:2]}
    dev_per_stratum[strata_drawn[2]] = 4  # documented in DATA_SUMMARY.md

    by_stratum: Dict[ScenarioType, List[str]] = {s: [] for s in STRATUM_ORDER}
    for cand in seeds:
        by_stratum[cand.scenario_type].append(cand.seed_id)

    dev_ids: List[str] = []
    blind_ids: List[str] = []
    blind_per_stratum: Dict[str, List[str]] = {}
    dev_per_stratum_out: Dict[str, List[str]] = {}
    for stratum in STRATUM_ORDER:
        ids = sorted(by_stratum[stratum])  # SEED-<NNN> lexicographic == numeric
        n_dev = dev_per_stratum[stratum]
        n_blind = len(ids) - n_dev
        blind = sorted(rng.sample(ids, n_blind))
        dev = sorted(set(ids) - set(blind))
        assert len(dev) == n_dev and len(blind) == n_blind
        dev_ids.extend(dev)
        blind_ids.extend(blind)
        dev_per_stratum_out[stratum.value] = dev
        blind_per_stratum[stratum.value] = blind

    dev_ids = sorted(dev_ids)
    blind_ids = sorted(blind_ids)
    assert len(dev_ids) == N_DEV and len(blind_ids) == N_BLIND
    assert not (set(dev_ids) & set(blind_ids))
    return {
        "development_seed_ids": dev_ids,
        "blind_seed_ids": blind_ids,
        "split_seed": split_seed,
        "strata_drawn": [s.value for s in strata_drawn],
        "dev_per_stratum": dev_per_stratum_out,
        "blind_per_stratum": blind_per_stratum,
    }


# ---------------------------------------------------------------------------
# Split guard
# ---------------------------------------------------------------------------


def load_split_manifest(path: Optional[str] = None, role: Optional[str] = None) -> SplitManifest:
    """Load + schema-validate the split manifest.

    ``role`` (optional) must be "development" or "blind"; it only
    validates the role value -- access checks are done by
    ``assert_split_access``.
    """
    if role is not None and role not in ("development", "blind"):
        raise ValueError(f"unknown role {role!r}; expected 'development' or 'blind'")
    path = path or DEFAULT_MANIFEST_PATH
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return SplitManifest.from_dict(data)


def assert_split_access(
    path_or_seed: Any,
    role: str,
    manifest: Optional[SplitManifest] = None,
) -> None:
    """Hard blind-split guard.

    role="development" may NOT open a blind-listed seed id or any file
    whose basename contains a blind-listed SEED-<NNN> token; such access
    raises BlindSplitAccessError.  role="blind" is unrestricted (the
    guard is one-directional by design).  Unknown roles raise
    ValueError.
    """
    if role not in ("development", "blind"):
        raise ValueError(f"unknown role {role!r}; expected 'development' or 'blind'")
    if role == "blind":
        return
    m = manifest if manifest is not None else load_split_manifest()
    blind = set(m.blind_seed_ids)
    s = os.fspath(path_or_seed) if not isinstance(path_or_seed, str) else path_or_seed
    if _SEED_TOKEN_RE.fullmatch(s):
        tokens = [s]
    else:
        tokens = _SEED_TOKEN_RE.findall(os.path.basename(s))
    bad = sorted(t for t in tokens if t in blind)
    if bad:
        raise BlindSplitAccessError(
            f"development-role access denied: blind-listed seed id(s) {bad} "
            f"referenced by {path_or_seed!r}"
        )


def load_seed_candidates_role(
    path: str,
    role: str,
    split_path: Optional[str] = None,
) -> List[Any]:
    """Role-routed seed loading: the ONLY sanctioned way seed manifests are
    opened by role-aware code (registry / builder / audit runner).

    In role="development" the manifest must contain NO blind-listed seed id:
    loading the full ``seed_candidates.jsonl`` under the development role
    raises ``BlindSplitAccessError``.  Development code must use the shipped
    dev-only manifest ``seed_candidates_development.jsonl`` (16 rows, no blind
    content).  The full manifest stays loadable with role="blind" (opt-in) --
    the guard is one-directional, matching ``assert_split_access``.
    """
    from .schemas import load_seed_candidates  # local import: avoid cycle

    manifest = load_split_manifest(split_path) if role == "development" else None
    # file-level guard first (basename tokens), then per-record seed ids
    assert_split_access(path, role, manifest=manifest)
    seeds = load_seed_candidates(path)
    if role == "development":
        blind = set(manifest.blind_seed_ids)  # type: ignore[union-attr]
        bad = sorted(s.seed_id for s in seeds if s.seed_id in blind)
        if bad:
            raise BlindSplitAccessError(
                f"development-role seed load refused: {path} contains "
                f"blind-listed seed id(s) {bad}; use the dev-only manifest "
                f"({DEFAULT_DEV_SEED_PATH}) instead"
            )
    return seeds


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def _relpath(path: str, start: str = REPO_ROOT) -> str:
    """os.path.relpath that falls back to the absolute path on drive mismatch.

    Always returns forward slashes so the emitted artifacts are
    byte-identical across platforms.
    """
    try:
        return os.path.relpath(path, start).replace(os.sep, "/")
    except ValueError:  # Windows: different mount points
        return os.path.abspath(path).replace(os.sep, "/")


def _markdown_table(header: List[str], rows: List[List[Any]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def write_data_summary(
    report_path: str,
    pool: Dict[str, Any],
    seeds: List[_Candidate],
    split: Dict[str, Any],
    seed_candidates_path: str,
    split_manifest_path: str,
    split_seed: int,
    stratum_question_counts: Optional[Dict[str, int]] = None,
) -> None:
    lines: List[str] = []
    lines.append("# ClearEval counterfactual-validity overlay -- DATA_SUMMARY (Task 1)")
    lines.append("")
    lines.append(f"- Algorithm: `{ALGORITHM_VERSION}` (see `seed_selector.py` module docstring for full rules)")
    lines.append(f"- Split seed: `{split_seed}` (RNG = `random.Random(split_seed)`)")
    lines.append(f"- Corpus: 253 OEQ questions x 13 frozen 1-shot models (dataset/Q+AR)")
    lines.append("")
    lines.append("All content selection is mechanical (regex/keyword/eligibility rules).")
    lines.append("No ClearEval gold, expert labels, mutation labels, or scorer thresholds")
    lines.append("were used to select or generate content.")
    lines.append("")

    # 1. Stratum definitions + question-level counts (recomputed at run time via
    #    derive_scenario_type -- never hardcoded; final-review finding #10).
    counts = stratum_question_counts or _default_stratum_question_counts()
    lines.append("## 1. Scenario strata (definition + question-level counts)")
    lines.append("")
    lines.append("| Stratum | Definition | Questions |")
    lines.append("|---|---|---|")
    lines.append(
        f"| ERROR_CORRECTION | question text matches `错误|纠正|纠错|排查|失败|修正|不妥|不当|问题所在` | {counts['ERROR_CORRECTION']} |"
    )
    lines.append(
        f"| COMPLEX_GENERATION | not ERROR_CORRECTION and `len(marker_query_targets) >= 4` | {counts['COMPLEX_GENERATION']} |"
    )
    lines.append(
        f"| SIMPLE_GENERATION | remaining questions | {counts['SIMPLE_GENERATION']} |"
    )
    lines.append("")
    lines.append(
        "Counts are derived per question with `derive_scenario_type(question_text, "
        "len(marker_query_targets))` over `question_final.json` (253 questions); the "
        "table is regenerated, never hardcoded."
    )
    lines.append("")

    # 2. Input hashes
    lines.append("## 2. Input files (sha256)")
    lines.append("")
    for path, digest in sorted(pool["input_hashes"].items()):
        lines.append(f"- `{_relpath(path)}` : `{digest}`")
    lines.append("")

    # 3. Eligibility + pool
    lines.append("## 3. Eligibility pre-filter (mechanical) and pool")
    lines.append("")
    lines.append("Eligibility rules (a)-(e) as documented in `seed_selector.py` rule 4:")
    lines.append("- (a) response record exists for (model, question_id);")
    lines.append("- (b) response_text non-empty after strip;")
    lines.append("- (c) evaluation record exists;")
    lines.append("- (d) usable totals present for completeness AND correctness AND effectiveness;")
    lines.append("- (e) `correctness.critical_warnings` empty or absent.")
    lines.append("")
    total_tried = 13 * 253
    total_eligible = len(pool["candidates"])
    total_rejected = total_tried - total_eligible
    lines.append(f"- Candidate pairs tried: `{total_tried}` (13 x 253)")
    lines.append(f"- Eligible: `{total_eligible}`")
    lines.append(f"- Rejected: `{total_rejected}` by reason:")
    lines.append("")
    rows = [[reason, count] for reason, count in sorted(pool["rejections"].items())]
    lines.append(_markdown_table(["Rejection reason", "Count"], rows))
    lines.append("")
    lines.append("Eligible pool per model:")
    lines.append("")
    rows = [[m, pool["per_model_eligible"][m]] for m in MODEL_NAMES]
    lines.append(_markdown_table(["Model", "Eligible candidates"], rows))
    lines.append("")
    lines.append("Eligible pool per stratum:")
    lines.append("")
    rows = [[s, pool["per_stratum_pool"].get(s, 0)] for s in [x.value for x in STRATUM_ORDER]]
    lines.append(_markdown_table(["Stratum", "Eligible candidates"], rows))
    lines.append("")
    lo, hi = pool["cc_range"]
    t1, t2 = pool["bucket_boundaries"]
    lines.append(f"- CCE total range over eligible pool: `[{lo:.4f}, {hi:.4f}]`")
    lines.append(f"- Bucket boundaries (equal-width thirds): LOW `< {t1:.4f}`, MID `< {t2:.4f}`, HIGH `>= {t2:.4f}`")
    lines.append("")

    # 4. Derivation rule summaries (method family + labeling)
    lines.append("## 4. Derivation rules (see `seed_selector.py` docstring for full tables)")
    lines.append("")
    lines.append("**clearing_method_family** -- first match wins over question text:")
    lines.append("")
    lines.append(
        "`CUBIC, PEGASOS, iDISCO, FDISCO, uDISCO, 3DISCO, DISCO, MACS, eFLASH, CLARITY, "
        "SHANEL, SeeDB, Scale (ScaleS/Scale), SWITCH, SOLVENT_BASED (甲醇/有机溶剂), UNKNOWN`"
    )
    lines.append("")
    lines.append("**labeling_requirement** -- text keywords + marker-name fallback:")
    lines.append("")
    lines.append(
        "transgenic signal = text `转基因|荧光蛋白|报告基因|遗传标记|外源基因|GFP|YFP|Thy1|tdTomato|Ai14|Cre|AAV` "
        "or any marker_name matching `GFP|YFP|Thy1|tdTomato|Ai14|reporter|Cre`; "
        "immuno signal = text `抗体|免疫`.  MIXED if transgenic signal and (immuno signal or "
        "`n_targets >= 4`); else TRANSGENIC / IMMUNOLABELING / UNKNOWN."
    )
    lines.append("")

    # 5. Selection algorithm
    lines.append("## 5. Selection algorithm (greedy round-robin, RNG-free)")
    lines.append("")
    lines.append(
        "Per stratum, 8 rounds; round r is led by dimension "
        "`DIMENSIONS[r % 5]` (`sample_tier, source_model, clearing_method_family, "
        "labeling_requirement, cce_bucket`).  Each round picks the unselected candidate with "
        "the smallest `(count[lead], sum(counts over other dims), question_id, source_model)` "
        "lexicographic key.  seed_ids are then assigned `SEED-001..024` sorted by "
        "(stratum rank, question_id, source_model)."
    )
    lines.append("")

    # 6. Chosen seeds per stratum
    lines.append("## 6. Chosen seeds (24; 8 per stratum)")
    lines.append("")
    for stratum in STRATUM_ORDER:
        stratum_seeds = [c for c in seeds if c.scenario_type is stratum]
        lines.append(f"### {stratum.value} ({len(stratum_seeds)} seeds)")
        lines.append("")
        rows = []
        for c in stratum_seeds:
            rows.append(
                [
                    c.seed_id,
                    c.question_id,
                    c.source_model,
                    c.sample_tier,
                    c.clearing_method_family,
                    c.labeling_requirement,
                    c.n_marker_targets,
                    c.cce_bucket,
                    f"{c.cce_total:.4f}",
                ]
            )
        lines.append(
            _markdown_table(
                ["seed_id", "qid", "model", "sample_tier", "method_family", "labeling", "n_targets", "cce_bucket", "cce_total"],
                rows,
            )
        )
        lines.append("")

    # 7. Split
    lines.append("## 7. Development / blind split (seeds only)")
    lines.append("")
    lines.append(f"- RNG drew stratum order: `{', '.join(split['strata_drawn'])}`")
    lines.append(
        f"- The first two drawn strata keep 6 development seeds each; the third "
        f"(`{split['strata_drawn'][2]}`) keeps 4."
    )
    lines.append("")
    lines.append("| Stratum | development | blind |")
    lines.append("|---|---|---|")
    for stratum in [s.value for s in STRATUM_ORDER]:
        lines.append(
            f"| {stratum} | {len(split['dev_per_stratum'][stratum])} | "
            f"{len(split['blind_per_stratum'][stratum])} |"
        )
    lines.append("")
    lines.append("**development_seed_ids** (16):")
    lines.append("")
    lines.append("`" + ", ".join(split["development_seed_ids"]) + "`")
    lines.append("")
    lines.append("**blind_seed_ids** (8):")
    lines.append("")
    lines.append("`" + ", ".join(split["blind_seed_ids"]) + "`")
    lines.append("")

    # 8. Output files (sha256) -- basenames only, so the report stays
    # byte-identical regardless of where it is generated
    lines.append("## 8. Output files (sha256)")
    lines.append("")
    for path in (seed_candidates_path, split_manifest_path):
        lines.append(f"- `{os.path.basename(path)}` : `{_sha256_file(path)}`")
    lines.append("")

    with open(report_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# run() + CLI
# ---------------------------------------------------------------------------


def run(
    data_root: str,
    output_dir: str,
    report_dir: str,
    split_seed: int = DEFAULT_SPLIT_SEED,
) -> Dict[str, Any]:
    """Execute the full pipeline; returns a summary dict."""
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(report_dir, exist_ok=True)

    pool = build_pool(data_root)
    selected = select_seeds(pool)
    seeds = assign_seed_ids(selected)
    assert len(seeds) == N_TOTAL_SEEDS
    per_stratum = collections.Counter(c.scenario_type.value for c in seeds)
    assert all(per_stratum[s.value] == N_SEEDS_PER_STRATUM for s in STRATUM_ORDER)

    seed_records = [
        SeedCandidate(
            seed_id=c.seed_id,
            question_id=c.question_id,
            scenario_type=c.scenario_type,
            source_model=c.source_model,
            source_file=c.source_file,
            response_text=c.response_text,
            question_mode=QUESTION_MODE,
            sample_tier=c.sample_tier,
            clearing_method_family=c.clearing_method_family,
            labeling_requirement=c.labeling_requirement,
            n_marker_targets=c.n_marker_targets,
            cce_scores=c.cce_scores,
        )
        for c in seeds
    ]

    seed_path = os.path.join(output_dir, "seed_candidates.jsonl")
    write_seed_candidates(seed_path, seed_records)

    # dev-only seed manifest (16 development rows, NO blind content): the
    # role-routed seed-loading API (load_seed_candidates_role) points
    # development-role code here, so blind seed response texts are never
    # opened by development-role tools (final-review finding #15).
    split = make_split(seeds, split_seed)
    dev_seed_ids = set(split["development_seed_ids"])
    dev_seed_path = os.path.join(output_dir, "seed_candidates_development.jsonl")
    write_seed_candidates(dev_seed_path, [s for s in seed_records if s.seed_id in dev_seed_ids])

    manifest_path = os.path.join(output_dir, "split_manifest.json")
    manifest = SplitManifest(
        development_seed_ids=split["development_seed_ids"],
        blind_seed_ids=split["blind_seed_ids"],
        split_seed=split["split_seed"],
        created_from=_sha256_file(seed_path),
        frozen_prompt_sha256=None,
    )
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest.to_dict(), fh, ensure_ascii=False, sort_keys=True, indent=2)
        fh.write("\n")

    report_path = os.path.join(report_dir, "DATA_SUMMARY.md")
    questions = load_questions(data_root)
    question_counts: "collections.Counter[str]" = collections.Counter()
    for r in questions.values():
        qtext = r["question"]
        n_targets = len(r.get("marker_query_targets") or [])
        question_counts[derive_scenario_type(qtext, n_targets).value] += 1
    write_data_summary(
        report_path,
        pool,
        seeds,
        split,
        seed_path,
        manifest_path,
        split_seed,
        stratum_question_counts={sc.value: question_counts[sc.value] for sc in STRATUM_ORDER},
    )

    return {
        "seed_candidates_path": seed_path,
        "dev_seed_candidates_path": dev_seed_path,
        "split_manifest_path": manifest_path,
        "report_path": report_path,
        "n_seeds": len(seeds),
        "per_stratum": dict(per_stratum),
        "n_eligible": len(pool["candidates"]),
        "rejections": dict(pool["rejections"]),
        "development_seed_ids": split["development_seed_ids"],
        "blind_seed_ids": split["blind_seed_ids"],
        "seed_candidates_sha256": manifest.created_from,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="seed_selector",
        description="ClearEval counterfactual-validity overlay: select 24 seeds + split 16/8.",
    )
    parser.add_argument("--data-root", default=REPO_ROOT, help="repo root containing dataset/")
    parser.add_argument(
        "--output-dir", default=os.path.join(PKG_DIR, "manifests"), help="where seed_candidates.jsonl + split_manifest.json go"
    )
    parser.add_argument("--report-dir", default=os.path.join(PKG_DIR, "reports"), help="where DATA_SUMMARY.md goes")
    parser.add_argument("--split-seed", type=int, default=DEFAULT_SPLIT_SEED, help="split RNG seed")
    args = parser.parse_args(argv)

    summary = run(
        data_root=args.data_root,
        output_dir=args.output_dir,
        report_dir=args.report_dir,
        split_seed=args.split_seed,
    )
    print(f"seeds written : {summary['seed_candidates_path']} ({summary['n_seeds']})")
    print(f"per stratum   : {summary['per_stratum']}")
    print(f"eligible pool : {summary['n_eligible']}  rejections: {summary['rejections']}")
    print(f"manifest      : {summary['split_manifest_path']}")
    print(f"dev seeds     : {len(summary['development_seed_ids'])}  blind seeds: {len(summary['blind_seed_ids'])}")
    print(f"report        : {summary['report_path']}")
    print(f"created_from  : {summary['seed_candidates_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
