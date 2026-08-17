"""ClearEval counterfactual-validity overlay -- mutation proposal builder (Task 2).

Builds, for each seed response: 1 semantics-preserving variant
(``expected_relation=EQUIVALENT``) and 2 single-defect variants
(``expected_relation`` DEGRADED or HARD_FAIL) -- 24 seeds -> 72
``MutationProposal`` records, ALL written with
``review_status = PENDING_REVIEW``, empty ``reviewer_ids`` and
``adjudication_status = PENDING``.

Every mutation is produced by a **span-level operator** that edits the
seed's ``response_text`` directly (no LLM, no network), records the exact
original/mutated char spans and labels the semantic field that changed.
ClearEval's gold / expert / mutation labels and scorer thresholds are never
consulted.  Evidence-backed operators cite knowledge-base rows by evidence id
(``kb:<file>:<key>``).

--------------------------------------------------------------------------------
Operators + expected-relation rules (documented; deterministic)
--------------------------------------------------------------------------------
1. EQUIVALENT
   - wording/formatting-only edit; every change is a SurfaceEdit;
     ``changed_field_paths = []``; severity NONE.
   - ``expected_affected_components`` is set to ``[S_METHOD]`` only because
     the schema requires a non-empty list; the semantic marker for "no score
     impact expected" is severity NONE + relation EQUIVALENT.
2. REQUIRED_INFORMATION_OMISSION  (DEGRADED, MODERATE)
   - replace the declared ``Time: <value>`` of one step with
     "Time: unspecified" -> the step's declared duration parameter is gone.
3. STEP_ORDER_OR_CHEMISTRY_CONFLICT (DEGRADED, MODERATE)
   - swap two adjacent numbered sub-steps within one section.
4. TARGET_MARKER_MISMATCH (DEGRADED, MODERATE)
   - replace a question-target marker mention with a marker NOT in the
     question's marker_query_targets.
5. METHOD_FLUOROPHORE_CONFLICT (DEGRADED, MODERATE)
   - replace a compatible fluorophore with one the KB rates <= 0.25 for the
     stated clearing method (method_fluro_compati.json).
6. SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT (HARD_FAIL, CRITICAL)
   - replace the stated clearing method with the KB method whose reference RI
     is furthest from the sample's native RI (method_ri_ref.json vs
     tissue_ri.json); cite the time_kb.json support gate too when the
     replacement (method, tier) row is absent.
7. CLEARING_TIME_OUT_OF_RANGE (HARD_FAIL, CRITICAL)
   - replace the dominant clearing duration with a value strictly above the
     KB [min, max] range for the stated method + tier (time_kb.json); when no
     row applies, the documented unsupported-tier gate (constant "45 days")
     is used.

Fallbacks: when an operator cannot find a textual target it emits a
*documented* template insertion instead of failing silently (see
MUTATION_BUILD.md).  Fallback metadata is persisted on every proposal record
(``operator_fallback_used`` / ``operator_fallback_note``) so the validator and
reports read it from the manifest, not from markdown prose.  No fallback is
expected to trigger for the frozen seeds; the validator lists every one that
does.

--------------------------------------------------------------------------------
Family -> seed assignment (deterministic, seeded RNG, documented)
--------------------------------------------------------------------------------
FAMILIES = the 6 families in canonical order; seeds sorted by seed_id.
rng = random.Random(20260817); order = list(range(24)); rng.shuffle(order).
Seed at shuffled index ``i`` gets FAMILIES[(2*i) % 6] and FAMILIES[(2*i+1) % 6],
so each family is used exactly 8 times and every seed gets exactly 2 distinct
families.  This is the only RNG consumption of the builder.

--------------------------------------------------------------------------------
Determinism
--------------------------------------------------------------------------------
Output is written with ``schemas.write_mutation_proposals`` (sort_keys + UTF-8
+ LF); pair ids are assigned after a fixed sort; no timestamps are written.
Two runs in identical trees produce byte-identical files.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import os
import random
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

try:  # run as `python -m diagnostics.cleareval_cf.mutation_builder`
    from .schemas import (
        AdjudicationStatus,
        ComponentId,
        ExpectedRelation,
        MutationFamily,
        MutationProposal,
        ReviewStatus,
        SeedCandidate,
        SeverityLevel,
        SurfaceEdit,
        TextSpan,
        ValidationError,
        write_mutation_proposals,
    )
    from .seed_selector import DEFAULT_DEV_SEED_PATH, load_seed_candidates_role, load_split_manifest
except ImportError:  # run as `python diagnostics/cleareval_cf/mutation_builder.py`
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from schemas import (  # type: ignore
        AdjudicationStatus,
        ComponentId,
        ExpectedRelation,
        MutationFamily,
        MutationProposal,
        ReviewStatus,
        SeedCandidate,
        SeverityLevel,
        SurfaceEdit,
        TextSpan,
        ValidationError,
        write_mutation_proposals,
    )
    from seed_selector import (  # type: ignore
        DEFAULT_DEV_SEED_PATH,
        load_seed_candidates_role,
        load_split_manifest,
    )

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(PKG_DIR))
KB_ROOT = os.path.join(REPO_ROOT, "KnowledgeBase")

DEFAULT_SEED_PATH = os.path.join(PKG_DIR, "manifests", "seed_candidates.jsonl")
DEFAULT_DEV_SEED_PATH = os.path.join(PKG_DIR, "manifests", "seed_candidates_development.jsonl")
DEFAULT_SPLIT_PATH = os.path.join(PKG_DIR, "manifests", "split_manifest.json")
DEFAULT_PROPOSALS_PATH = os.path.join(PKG_DIR, "manifests", "mutation_proposals.jsonl")
DEFAULT_GOLD_PATH = os.path.join(PKG_DIR, "manifests", "reviewed_gold.jsonl")
DEFAULT_BUILD_REPORT = os.path.join(PKG_DIR, "reports", "MUTATION_BUILD.md")

QUESTION_FILE = os.path.join("dataset", "Q+AR", "src", "question_final.json")

SPLIT_RNG_SEED = 20260817
MUTATION_OPERATOR_VERSION = "v1.0"

FAMILIES = [
    MutationFamily.CLEARING_TIME_OUT_OF_RANGE.value,
    MutationFamily.METHOD_FLUOROPHORE_CONFLICT.value,
    MutationFamily.REQUIRED_INFORMATION_OMISSION.value,
    MutationFamily.SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT.value,
    MutationFamily.STEP_ORDER_OR_CHEMISTRY_CONFLICT.value,
    MutationFamily.TARGET_MARKER_MISMATCH.value,
]


# ---------------------------------------------------------------------------
# Knowledge base access (stdlib only)
# ---------------------------------------------------------------------------


class KB:
    """Loads the KnowledgeBase JSON files once; exposes deterministic lookups.

    Evidence id grammar: ``kb:<basename>:<qualified-key>``.
    """

    # Tissue-group keys that classify to a representative *leaf* in
    # tissue_ri.json (the file stores subtype -> RI *inside* groups).
    TISSUE_CANON = {"brain": "whole_brain"}

    def __init__(self, kb_root: str = KB_ROOT) -> None:
        self.kb_root = kb_root
        self.time_kb = _load_json_file(os.path.join(kb_root, "time_kb.json"))
        self.fluro_rows = _load_json_file(os.path.join(kb_root, "method_fluro_compati.json"))
        self.fluro = {row["method"]: row for row in self.fluro_rows}
        self.ri_ref = _load_json_file(os.path.join(kb_root, "method_ri_ref.json"))["ri_ref"]
        self.tissue_ri = _load_json_file(os.path.join(kb_root, "tissue_ri.json"))["tissue_ri_database"]
        leaves: set = set()
        for group in self.tissue_ri.get("tissues", {}).values():
            if isinstance(group, dict):
                leaves.update(k for k in group if k != "note")
        self._tissue_leaves = leaves

    # -- lookups ------------------------------------------------------------

    def fluro_compat(self, method: str, dye: str) -> Optional[float]:
        row = self.fluro.get(method)
        if row is None:
            return None
        val = row.get(dye)
        return float(val) if isinstance(val, (int, float)) else None

    def time_lookup(self, method: str) -> Dict[str, Any]:
        return self.time_kb.get("lookup", {}).get(method, {})

    def time_row_for_tier(self, method: str, tier: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """Exact (method, tier) row; else best token-overlap tier; else None.

        Returns ``(row, tier_reference)`` where ``tier_reference`` is the
        resolved tier code (used in the evidence id).  ``(None, tier)`` when no
        row applies -> the UNSUPPORTED support-gate evidence path.
        """
        rows = self.time_lookup(method)
        if tier in rows:
            return rows[tier], tier
        tier_tokens = _non_tier_tokens(tier)
        best: Optional[Tuple[int, str]] = None
        for row_tier in rows:
            overlap = len(tier_tokens & _non_tier_tokens(row_tier))
            if overlap >= 2 and (best is None or overlap > best[0]):
                best = (overlap, row_tier)
        if best is not None:
            return rows[best[1]], best[1]
        return None, tier

    def ri_ref_value(self, method: str) -> Optional[float]:
        entry = self.ri_ref.get(method)
        return float(entry["ri"]) if entry else None

    def tissue_canon(self, tissue_key: str) -> str:
        """Canonical tissue leaf key used for RI + evidence id."""
        if tissue_key == "default":
            return "default"
        if tissue_key in self._tissue_leaves:
            return tissue_key
        canon = self.TISSUE_CANON.get(tissue_key)
        return canon if canon in self._tissue_leaves else "default"

    def tissue_ri_value(self, tissue_key: str) -> float:
        canon = self.tissue_canon(tissue_key)
        if canon == "default":
            return float(self.tissue_ri.get("default_ri", 1.48))
        for group in self.tissue_ri.get("tissues", {}).values():
            if isinstance(group, dict) and canon in group:
                return float(group[canon])
        return float(self.tissue_ri.get("default_ri", 1.48))

    # -- evidence ids --------------------------------------------------------

    def evidence_id_time(self, method: str, tier_reference: str) -> str:
        return f"kb:time_kb.json:{method}|{tier_reference}"

    def evidence_id_time_unsupported(self, method: str, tier: str) -> str:
        return f"kb:time_kb.json:{method}|UNSUPPORTED:{tier}"

    def evidence_id_fluro(self, method: str) -> str:
        return f"kb:method_fluro_compati.json:{method}"

    def evidence_id_ri_ref(self, method: str) -> str:
        return f"kb:method_ri_ref.json:{method}"

    def evidence_id_tissue(self, tissue_key: str) -> str:
        canon = self.tissue_canon(tissue_key)
        if canon == "default":
            return "kb:tissue_ri.json:default_ri"
        return f"kb:tissue_ri.json:{canon}"


def _load_json_file(path: str) -> Any:
    import json

    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _non_tier_tokens(tier: str) -> set:
    return {tok for tok in tier.split("_") if not re.fullmatch(r"T\d+[A-Z0-9]*", tok)}


# ---------------------------------------------------------------------------
# Span utilities
# ---------------------------------------------------------------------------


def apply_edits(original: str, edits: List[Tuple[int, int, str]]) -> Tuple[str, List[Tuple[int, int, str]]]:
    """Apply (start, end, new_text) edits in ORIGINAL offsets.

    Edits must be pairwise disjoint and sorted by start.  Returns
    ``(mutated_text, mutated_spans)`` with mutated spans
    ``(m_start, m_end, new_text)`` offset into ``mutated_text``.
    """
    edits = sorted(edits, key=lambda e: (e[0], e[1]))
    prev_end = 0
    out: List[str] = []
    mut_spans: List[Tuple[int, int, str]] = []
    m_cur = 0
    for start, end, new_text in edits:
        if start < prev_end:
            raise ValidationError(f"overlapping edits at start={start}, prev_end={prev_end}")
        if not (0 <= start < end <= len(original)):
            raise ValidationError(f"edit out of original bounds: {start}..{end} (len {len(original)})")
        prefix = original[prev_end:start]
        out.append(prefix)
        m_cur += len(prefix)
        m_start = m_cur
        out.append(new_text)
        m_cur += len(new_text)
        mut_spans.append((m_start, m_cur, new_text))
        prev_end = end
    out.append(original[prev_end:])
    return "".join(out), mut_spans


def region_of(original: str, edited: str) -> List[Tuple[int, int]]:
    """Diff-based changed regions of ``original`` (offsets into original)."""
    import difflib

    sm = difflib.SequenceMatcher(a=original, b=edited, autojunk=False)
    regions: List[Tuple[int, int]] = []
    for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        regions.append((i1, i2))
    return regions


# ---------------------------------------------------------------------------
# Text extraction (bilingual seed responses)
# ---------------------------------------------------------------------------

METHOD_TOKENS = [
    "iDISCO+", "BoneClear", "ClearT2", "FlyClear", "PEGASOS", "ScaleS",
    "ClearSee", "3DISCO", "FDISCO", "uDISCO", "SeeDB2", "Ce3D", "EyeCi",
    "FOCM", "SWITCH", "CLARITY", "SHANEL", "eFLASH", "SOLID", "MACS", "TDE",
    "CUBIC", "DISCO",
]
_METHOD_RE = re.compile("|".join(re.escape(t) for t in sorted(METHOD_TOKENS, key=len, reverse=True)))

# Methods present in time_kb.json (the "stated method" domain we can act on).
METHODS_KB_KEYS = frozenset(
    [
        "BoneClear", "CUBIC", "Ce3D", "ClearSee", "ClearT2", "FDISCO",
        "FOCM", "MACS", "PEGASOS", "SOLID", "SWITCH", "ScaleS", "SeeDB2",
        "TDE", "iDISCO+", "uDISCO",
    ]
)


def _is_ascii_word(char: str) -> bool:
    return char.isascii() and (char.isalnum() or char == "_")


def _token_bounded(m: "re.Match[str]", text: str) -> bool:
    """True when the match isn't embedded inside an ASCII word."""
    s, e = m.start(), m.end()
    if s > 0 and _is_ascii_word(text[s - 1]):
        return False
    if e < len(text) and _is_ascii_word(text[e]):
        return False
    return True


_STATED_METHOD_PATTERNS: List[Tuple[str, "re.Pattern[str]"]] = [
    ("bold_chosen", re.compile(r"\*\*\s*Chosen\s*Method\s*:\s*\*?\*?\s*([A-Za-z0-9+]+)")),
    ("chosen", re.compile(r"Chosen\s*Method\s*:\s*([A-Za-z0-9+]+)")),
    ("cn_method", re.compile(r"(?:所选组织透明方法|透明(?:组织)?方法|ClearingMethod|透明化方法|透明方法)[：:]\s*[*]?([A-Za-z0-9+]+)")),
    ("cn_switch", re.compile(r"(?:透明化方法更换为|更换透明化为)\s*[*]?([A-Za-z0-9+]+)")),
]


def _normalize_method(token: str) -> Optional[str]:
    t = token.strip()
    if t in ("iDISCO", "iDISCO+"):
        return "iDISCO+"
    if t in ("SeeDB", "SeeDB2"):
        return "SeeDB2"
    if t in ("Scale", "ScaleS"):
        return "ScaleS"
    if t in METHODS_KB_KEYS:
        return t
    return None


def stated_method(text: str) -> Tuple[Optional[str], Optional[Tuple[int, int, str]]]:
    """Extract the declared clearing method (kb_key, span) from a response.

    Regex patterns first; count-based fallback (most frequent KB method token,
    tie -> earliest occurrence in the text).
    """
    for _name, pat in _STATED_METHOD_PATTERNS:
        m = pat.search(text)
        if m:
            key = _normalize_method(m.group(1))
            if key is not None:
                return key, (m.start(1), m.end(1), m.group(1))
    matches = []
    for m in _METHOD_RE.finditer(text):
        if _token_bounded(m, text):
            matches.append(m)
    if not matches:
        return None, None
    counts: "collections.Counter[str]" = collections.Counter(m.group(0) for m in matches)
    best_token = max(sorted(counts), key=lambda t: counts[t])
    for m in matches:
        if m.group(0) == best_token:
            key = _normalize_method(best_token)
            return key, (m.start(), m.end(), m.group(0))
    return None, None


# ---------------------------------------------------------------------------
# Tissue native RI classifier (question text -> tissue_ri.json key)
# ---------------------------------------------------------------------------

# (keyword, tissue key) -- first match wins; CJK/specific entries first.
# ASCII keywords use word-boundary matching so 'plant' does not hit 'implant'.
TISSUE_KEYWORDS: List[Tuple[str, str]] = [
    ("拟南芥", "plant"), ("阿拉伯芥", "plant"), ("幼苗", "plant"), ("seedling", "plant"),
    ("arabidopsis", "plant"), ("植物", "plant"), ("根系", "plant"), ("叶片", "plant"),
    ("plant", "plant"), ("叶子", "plant"),
    ("斑马鱼", "zebrafish"), ("zebrafish", "zebrafish"),
    ("线虫", "celegans"), ("c. elegans", "celegans"), ("nematode", "celegans"),
    ("worm", "celegans"),
    ("类器官", "organoid"), ("organoid", "organoid"),
    ("眼球", "eye_retina"), ("视网膜", "eye_retina"), ("eye", "eye_retina"),
    ("retina", "eye_retina"),
    ("胚胎", "embryo_whole"), ("embryo", "embryo_whole"),
    ("脊髓", "spinal_cord"), ("spinal", "spinal_cord"),
    ("心脏", "heart"), ("心肌", "heart"), ("cardiac", "heart"), ("heart", "heart"),
    ("皮肤", "skin"), ("skin", "skin"),
    ("胰腺", "pancreas"), ("胰岛", "pancreas"), ("pancreas", "pancreas"),
    ("前列腺", "prostate"), ("prostate", "prostate"),
    ("胎盘", "placenta"), ("placenta", "placenta"),
    ("肺", "lung"), ("肺泡", "lung"), ("lung", "lung"),
    ("淋巴结", "lymph_node"), ("淋巴", "lymph_node"), ("lymph", "lymph_node"),
    ("肝", "liver"), ("liver", "liver"),
    ("肾", "kidney"), ("kidney", "kidney"),
    ("肠", "intestine"), ("intestine", "intestine"),
    ("胃", "stomach"), ("stomach", "stomach"),
    ("脾", "spleen"), ("spleen", "spleen"),
    ("睾丸", "testis"), ("testis", "testis"),
    ("骨骼肌", "skeletal_muscle"), ("skeletal muscle", "skeletal_muscle"),
    ("肌", "skeletal_muscle"), ("muscle", "skeletal_muscle"),
    ("脂肪", "fat"), ("fat", "fat"),
    ("全脑", "brain"), ("脑", "brain"), ("皮层", "brain"), ("海马", "brain"),
    ("cortex", "brain"), ("hippocampus", "brain"), ("brain", "brain"),
    ("牙", "tooth"), ("tooth", "tooth"), ("股骨", "femur"), ("femur", "femur"),
    ("颅", "skull"), ("skull", "skull"), ("耳蜗", "cochlea"), ("cochlea", "cochlea"),
    ("骨", "bone"), ("bone", "bone"),
    ("黑色素瘤", "melanoma"), ("melanoma", "melanoma"),
    ("乳腺", "breast_cancer"), ("breast", "breast_cancer"),
    ("肿瘤", "tumor_dense"), ("癌", "tumor_dense"), ("瘤", "tumor_dense"),
    ("tumor", "tumor_dense"), ("tumour", "tumor_dense"),
]


def _kw_in(text: str, kw: str) -> bool:
    if kw.isascii():
        pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(kw) + r"(?![A-Za-z0-9])")
        return pat.search(text) is not None
    return kw in text


def classify_tissue(question_text: str) -> Tuple[str, str]:
    """Return ``(tissue_key, matched_keyword)``; default key when no match."""
    lower = question_text.lower()
    for kw, key in TISSUE_KEYWORDS:
        if _kw_in(lower, kw):
            return key, kw
    return "default", ""


# ---------------------------------------------------------------------------
# Marker / fluorophore lexicons
# ---------------------------------------------------------------------------

MARKER_TOKENS = [
    "SCRI Renaissance 2200", "Propidium iodide", "alpha-bungarotoxin",
    "Calcofluor White", "NeuroTrace 500", "Myosin VIIa", "C-FoS", "Npas4",
    "Alexa Fluor 405", "Alexa Fluor 488", "Alexa Fluor 546", "Alexa Fluor 555",
    "Alexa Fluor 568", "Alexa Fluor 594", "Alexa Fluor 633", "Alexa Fluor 647",
    "Alexa Fluor 680", "Alexa Fluor 750", "DyLight 405", "DyLight 488",
    "DyLight 550", "DyLight 594", "DyLight 649", "iFluor 594", "iFluor 647",
    "β-III Tubulin", "beta-III Tubulin", "TUJ1", "Tuj1", "Pan-Cytokeratin",
    "Pan-CK", "Contactin-2", "Cntn2", "Cx40", "HCN4", "MECA-79", "PECAM1",
    "CD31", "PNAd", "PGP9.5", "Insulin", "PDX1", "Glucagon", "α-Actinin",
    "cTnT", "Phalloidin", "RBPMS", "Brn3a", "POU4F1", "MAP2", "GFAP", "Ki67",
    "MKI67", "PCNA", "ChAT", "TH", "AMACR", "p63", "Lectin", "IB4",
    "TO-PRO-3", "EGFP", "YFP", "mCherry", "tdTomato", "RFP", "GFP", "DAPI",
    "Hoechst", "DiI", "DiO", "DiD", "FITC", "TRITC", "Cy3", "Cy5", "PE",
]
_MARKER_RE = re.compile("|".join(re.escape(t) for t in sorted(MARKER_TOKENS, key=len, reverse=True)))

DYE_TOKENS = [
    "SCRI Renaissance 2200", "Propidium iodide", "alpha-bungarotoxin",
    "Calcofluor White", "NeuroTrace 500", "Alexa Fluor 750", "Alexa Fluor 680",
    "Alexa Fluor 647", "Alexa Fluor 633", "Alexa Fluor 594", "Alexa Fluor 568",
    "Alexa Fluor 555", "Alexa Fluor 546", "Alexa Fluor 488", "Alexa Fluor 405",
    "DyLight 649", "DyLight 594", "DyLight 550", "DyLight 488", "DyLight 405",
    "iFluor 647", "iFluor 594", "TO-PRO-3", "tdTomato", "mCherry", "YFP",
    "EGFP", "GFP", "RFP", "DAPI", "Hoechst", "DiI", "DiO", "DiD", "FITC",
    "TRITC", "Cy5", "Cy3", "PE", "Phalloidin", "Lectin", "IB4",
]
_DYE_RE = re.compile("|".join(re.escape(t) for t in sorted(DYE_TOKENS, key=len, reverse=True)))

DISTRACTOR_MARKERS = sorted(
    [
        "α-Actinin", "CD11b", "CD31", "ChAT", "DAPI", "GFAP", "GFP",
        "Glucagon", "Hoechst", "Insulin", "Ki67", "Laminin", "MAP2",
        "mCherry", "Myosin VIIa", "NeuN", "PGP9.5", "Phalloidin", "RBPMS",
        "S100B", "TH", "TUJ1", "YFP",
    ]
)

# Preference order for the KB-incompatible fluorophore replacement.
CONFLICT_DYE_PREFERENCE = [
    "EGFP", "GFP", "YFP", "DiI", "DiO", "DiD", "SCRI Renaissance 2200", "tdTomato", "mCherry",
]


# ---------------------------------------------------------------------------
# Family -> seed assignment (deterministic, seeded RNG)
# ---------------------------------------------------------------------------


def family_assignment(seed_ids: List[str]) -> Dict[str, List[str]]:
    """See module docstring.  ``seed_ids`` are sorted seed ids."""
    assert seed_ids == sorted(seed_ids), "family_assignment expects sorted seed ids"
    rng = random.Random(SPLIT_RNG_SEED)  # the builder's ONLY RNG use
    order = list(range(len(seed_ids)))
    rng.shuffle(order)
    assignment: Dict[str, List[str]] = {}
    for i, si in enumerate(order):
        assignment[seed_ids[si]] = [FAMILIES[(2 * i) % 6], FAMILIES[(2 * i + 1) % 6]]
    return assignment


# ---------------------------------------------------------------------------
# Operator result
# ---------------------------------------------------------------------------


class _OpResult:
    __slots__ = (
        "family", "relation", "severity", "components", "changed_field_paths",
        "edits", "surface_edits", "evidence_ids", "location", "fallback_used",
        "fallback_note", "operator",
    )

    def __init__(
        self,
        family: MutationFamily,
        relation: ExpectedRelation,
        severity: SeverityLevel,
        components: List[ComponentId],
        changed_field_paths: List[str],
        edits: List[Tuple[int, int, str]],
        surface_edits: List[Tuple[int, int, str]],
        evidence_ids: List[str],
        location: str,
        operator: str,
        fallback_used: bool = False,
        fallback_note: str = "",
    ) -> None:
        self.family = family
        self.relation = relation
        self.severity = severity
        self.components = components
        self.changed_field_paths = changed_field_paths
        self.edits = edits
        self.surface_edits = surface_edits
        self.evidence_ids = evidence_ids
        self.location = location
        self.operator = operator
        self.fallback_used = fallback_used
        self.fallback_note = fallback_note


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------


def _first_token_match(text: str, pat: "re.Pattern[str]", bounded: bool) -> Optional["re.Match[str]"]:
    for m in pat.finditer(text):
        if bounded and not _token_bounded(m, text):
            continue
        return m
    return None


def _step_number_of(text: str, pos: int) -> str:
    line_start = text.rfind("\n", 0, pos) + 1
    m = re.match(r"\s*(\d+(?:\.\d+)?)", text[line_start:])
    return m.group(1) if m else ""


def op_equivalent(seed_text: str) -> _OpResult:
    """Semantics-preserving wording/formatting edit (first catalogue match).

    No scientific parameter value changes, so ``changed_field_paths = []`` and
    the change is recorded as a SurfaceEdit.
    """
    catalogue: List[Tuple[str, "re.Pattern[str]", str, str]] = [
        ("×-spacing", re.compile(r"(?<=\d)×(?=\d)"), " × ", "spacing around the × multiplication sign (formatting-only)"),
        ("℃->°C", re.compile(r"℃"), "°C", "degree-sign notation (formatting-only)"),
        ("µg->μg", re.compile(r"µg/mL"), "μg/ml", "unit case notation (formatting-only)"),
        ("1x->1×", re.compile(r"(?<![0-9])1x(?![A-Za-z])"), "1×", "multiplication sign notation for '1x' diluent (formatting-only)"),
        ("x->×", re.compile(r"(?<=[0-9])x(?=\s|[,(]|）|\)|$|[A-Z])"), "×", "multiplication sign notation (formatting-only)"),
        ("RT-annotate", re.compile(r"Temperature:\s*RT"), "Temperature: RT (room temperature)", "room-temperature annotation; value unchanged (wording-only)"),
    ]
    for name, pat, repl, note in catalogue:
        m = _first_token_match(seed_text, pat, bounded=False)
        if m is None:
            continue
        start, end = m.start(), m.end()
        mutated, _ = apply_edits(seed_text, [(start, end, repl)])
        if mutated == seed_text:
            continue
        return _OpResult(
            family=MutationFamily.STEP_ORDER_OR_CHEMISTRY_CONFLICT,  # placeholder, overridden by _assemble_equivalent
            relation=ExpectedRelation.EQUIVALENT,
            severity=SeverityLevel.NONE,
            components=[ComponentId.S_METHOD],
            changed_field_paths=[],
            edits=[(start, end, repl)],
            surface_edits=[(start, end, repl)],
            evidence_ids=[],
            location=f"formatting/wording micro-edit '{name}' at offset {start}",
            operator="equivalent_formatting_v1.0",
        )
    raise ValidationError("equivalent operator found no formatting/wording target (unexpected)")


def op_required_omission(seed_text: str) -> _OpResult:
    """Replace the declared ``Time: <value>`` of one step with 'unspecified'.

    Rule: one step loses its declared duration (a required parameter) ->
    DEGRADED (local omission; the protocol remains otherwise executable).
    """
    m = re.search(r"Time\s*:\s*[^()（）,，;；\r\n]+", seed_text)
    if m is None:
        m = re.search(r",?\s*Temperature\s*:\s*[^()（）,，;；\r\n]+", seed_text)
        if m is None:
            raise ValidationError("omission operator found no removable parameter clause")
        step_no = _step_number_of(seed_text, m.start())
        return _OpResult(
            family=MutationFamily.REQUIRED_INFORMATION_OMISSION,
            relation=ExpectedRelation.DEGRADED,
            severity=SeverityLevel.MODERATE,
            components=[ComponentId.COMPLETENESS, ComponentId.S_TIME],
            changed_field_paths=[f"protocol.steps[{step_no or 'step'}].temperature_value"],
            edits=[(m.start(), m.end(), "Temperature: unspecified")],
            surface_edits=[],
            evidence_ids=[],
            location=f"step {step_no or '?'} (temperature clause -> 'unspecified')",
            operator="omission_delete_param_v1.0",
            fallback_used=True,
            fallback_note="no 'Time:' clause found; replaced the step's Temperature clause instead",
        )
    start, end = m.start(), m.end()
    step_no = _step_number_of(seed_text, start)
    return _OpResult(
        family=MutationFamily.REQUIRED_INFORMATION_OMISSION,
        relation=ExpectedRelation.DEGRADED,
        severity=SeverityLevel.MODERATE,
        components=[ComponentId.COMPLETENESS, ComponentId.S_TIME],
        changed_field_paths=[f"protocol.steps[{step_no or 'step'}].duration_hours"],
        edits=[(start, end, "Time: unspecified")],
        surface_edits=[],
        evidence_ids=[],
        location=f"step {step_no or '?'} (duration clause -> 'unspecified')",
        operator="omission_delete_duration_v1.0",
    )


def op_step_order(seed_text: str) -> _OpResult:
    """Swap two adjacent numbered sub-steps within the section that has the most sub-steps."""
    step_re = re.compile(r"(?m)^([ \t]*)(\d+)\.(\d+)[.\s]+([^\r\n]*)")
    steps: List[Tuple[int, int, str, str, str]] = []
    for m in step_re.finditer(seed_text):
        start, end = m.start(), m.end()
        if end < len(seed_text) and seed_text[end] in "\r\n":
            end += 1
        steps.append((start, end, seed_text[start:end], m.group(2), m.group(3)))
    by_section: Dict[str, List[Tuple[int, int, str, str, str]]] = collections.defaultdict(list)
    for st in steps:
        by_section[st[3]].append(st)
    sections = [k for k, v in by_section.items() if len(v) >= 2]
    if not sections:
        raise ValidationError("step-order operator found no section with >= 2 numbered sub-steps")
    section = max(sections, key=lambda k: (len(by_section[k]), -int(k)))
    a, b = by_section[section][0], by_section[section][1]
    edits = [(a[0], a[1], b[2]), (b[0], b[1], a[2])]
    return _OpResult(
        family=MutationFamily.STEP_ORDER_OR_CHEMISTRY_CONFLICT,
        relation=ExpectedRelation.DEGRADED,
        severity=SeverityLevel.MODERATE,
        components=[ComponentId.CORRECTNESS],
        changed_field_paths=["protocol.steps.order"],
        edits=edits,
        surface_edits=[],
        evidence_ids=[],
        location=f"step {section}.{a[4]} <-> {section}.{b[4]} swapped",
        operator="step_order_swap_v1.0",
    )


def _normalize_marker(text: str) -> str:
    t = re.sub(r"\(.*?\)", "", text)
    t = re.sub(r"/.*", "", t)
    return re.sub(r"\s+", "", t).lower()


def op_target_marker(seed_text: str, targets: List[str]) -> _OpResult:
    """Replace a question-target marker mention with a NON-target distractor."""
    norm_targets: set = set()
    for t in targets:
        for part in str(t).split("|"):
            n = _normalize_marker(part)
            if n:
                norm_targets.add(n)
    target_matches = []
    for m in _MARKER_RE.finditer(seed_text):
        if not _token_bounded(m, seed_text):
            continue
        if _normalize_marker(m.group(0)) in norm_targets:
            target_matches.append(m)
    if not target_matches:  # fallback: first marker-ish token in the text
        for m in _MARKER_RE.finditer(seed_text):
            if _token_bounded(m, seed_text):
                target_matches.append(m)
                break
    if not target_matches:
        raise ValidationError("target-marker operator found no marker token in seed text")
    m = target_matches[0]
    matched = m.group(0)
    replacement = None
    for dist in DISTRACTOR_MARKERS:
        nd = _normalize_marker(dist)
        if dist != matched and nd not in norm_targets:
            replacement = dist
            break
    if replacement is None:
        raise ValidationError("target-marker operator found no usable distractor")
    return _OpResult(
        family=MutationFamily.TARGET_MARKER_MISMATCH,
        relation=ExpectedRelation.DEGRADED,
        severity=SeverityLevel.MODERATE,
        components=[ComponentId.CORRECTNESS, ComponentId.S_LABEL],
        changed_field_paths=["protocol.labels.marker_name"],
        edits=[(m.start(), m.end(), replacement)],
        surface_edits=[],
        evidence_ids=[],
        location=f"marker '{matched}' -> '{replacement}' (offset {m.start()})",
        operator="target_marker_replace_v1.0",
    )


def op_fluorophore_conflict(seed_text: str, method: str, kb: KB) -> _OpResult:
    """Replace a compatible fluorophore with a KB-incompatible one (compat <= 0.25)."""
    old: Optional[Tuple[int, str]] = None
    for m in _DYE_RE.finditer(seed_text):
        if not _token_bounded(m, seed_text):
            continue
        dye = m.group(0)
        compat = kb.fluro_compat(method, dye)
        if compat is not None and compat >= 0.6:
            old = (m.start(), dye)
            break
    if old is None:
        raise ValidationError(f"fluorophore operator found no compatible dye span for {method}")
    start, old_dye = old
    conflict = None
    for dye in CONFLICT_DYE_PREFERENCE:
        if dye == old_dye:
            continue
        compat = kb.fluro_compat(method, dye)
        if compat is not None and compat <= 0.25:
            conflict = dye
            break
    if conflict is None:
        raise ValidationError(f"fluorophore operator found no KB-incompatible dye for {method}")
    return _OpResult(
        family=MutationFamily.METHOD_FLUOROPHORE_CONFLICT,
        relation=ExpectedRelation.DEGRADED,
        severity=SeverityLevel.MODERATE,
        components=[ComponentId.S_LABEL, ComponentId.CORRECTNESS],
        changed_field_paths=["protocol.labels.fluorophore"],
        edits=[(start, start + len(old_dye), conflict)],
        surface_edits=[],
        evidence_ids=[kb.evidence_id_fluro(method)],
        location=f"fluorophore '{old_dye}' -> '{conflict}' (offset {start})",
        operator="method_fluorophore_conflict_v1.0",
    )


def op_sample_method_scope(seed_text: str, question_text: str, method: str, tier: str, kb: KB) -> _OpResult:
    """Replace the stated method with the KB method furthest from the sample RI.

    Evidence: method_ri_ref.json (per-method reference RI) vs tissue_ri.json
    (sample native RI); when (replacement, tier) has no time_kb.json row, the
    support-gate evidence is cited as well (hard scope violation).
    """
    tissue_key, kw = classify_tissue(question_text)
    ri_tissue = kb.tissue_ri_value(tissue_key)
    best: Optional[Tuple[float, str]] = None
    for cand in sorted(METHODS_KB_KEYS):
        if cand == method:
            continue
        ri = kb.ri_ref_value(cand)
        if ri is None:
            continue
        gap = abs(ri - ri_tissue)
        if best is None or gap > best[0]:
            best = (gap, cand)
    if best is None:
        raise ValidationError("sample-method operator found no candidate KB method")
    gap, replacement = best
    span: Optional[Tuple[int, int, str]] = None
    _mk, mspan = stated_method(seed_text)
    if mspan is not None:
        span = mspan
    if span is None:
        m = _first_token_match(seed_text, _METHOD_RE, bounded=True)
        if m is not None:
            span = (m.start(), m.end(), m.group(0))
    if span is None:
        raise ValidationError("sample-method operator found no method token to replace")
    evidence = [kb.evidence_id_ri_ref(replacement), kb.evidence_id_tissue(tissue_key)]
    row, _tref = kb.time_row_for_tier(replacement, tier)
    if row is None:
        evidence.append(kb.evidence_id_time_unsupported(replacement, tier))
    ri_repl = kb.ri_ref_value(replacement) or ri_tissue
    return _OpResult(
        family=MutationFamily.SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT,
        relation=ExpectedRelation.HARD_FAIL,
        severity=SeverityLevel.CRITICAL,
        components=[ComponentId.S_METHOD, ComponentId.S_TRANS, ComponentId.S_TIME],
        changed_field_paths=["protocol.method"],
        edits=[(span[0], span[1], replacement)],
        surface_edits=[],
        evidence_ids=evidence,
        location=f"method '{span[2]}' -> '{replacement}' (RI {ri_tissue:.2f} vs {ri_repl:.2f}, gap {gap:.3f})",
        operator="sample_method_scope_v1.0",
        fallback_note=f"tissue classified as '{tissue_key}' (keyword '{kw}')",
    )


TIME_VALUE_RE = re.compile(r"Time\s*:\s*([^()（）,，;；\r\n]+)")
_LABELING_CTX_RE = re.compile(r"一抗|二抗|抗体|antibody|Antibody|[Ss]taining|染色|[Ll]abeling|核染|DAPI|[Pp]rimary|[Ss]econdary|[Bb]locking|封闭|宿主", re.I)
_CLEARING_CTX_RE = re.compile(r"[Cc]lear|透明|清|[Dd]elipid|去脂|[Dd]ehydrat|脱水|[Bb]leach|脱色|[Ff]ructose|xylitol|[Hh]istodenz|[Qq]uadrol|urea|[Ss]odium deoxycholate|浸泡|[Rr]ehydrat|复水|[Tt]riton|甲醇", re.I)


def _estimate_hours(value: str) -> float:
    """Heuristic hours from a Time: value (ranges -> max; A×B multiplied)."""
    v = value
    mult = 1.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*[×x*]\s*(\d+(?:\.\d+)?)", v)
    if m:
        mult = float(m.group(1))
        v = v.replace(m.group(0), m.group(2))
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", v)]
    if not nums:
        return 0.0
    num = max(nums)
    if re.search(r"day|天", v, re.I):
        return num * 24.0 * mult
    if re.search(r"min", v, re.I):
        return num / 60.0 * mult
    return num * mult


def _replacement_in_style(original_value: str, hours: float) -> str:
    if re.search(r"day|天", original_value, re.I):
        return f"{int(round(hours / 24))} days"
    if re.search(r"min", original_value, re.I):
        return f"{int(round(hours * 60))} min"
    if original_value.rstrip().endswith("h"):
        return f"{int(round(hours))} h"
    if re.search(r"hour", original_value, re.I):
        return f"{int(round(hours))} hours"
    d = int(round(hours / 24))
    return f"{d} days" if d >= 1 else f"{int(round(hours))} hours"


def op_clearing_time(seed_text: str, method: str, tier: str, kb: KB) -> _OpResult:
    """Replace the dominant clearing duration with a KC-out-of-range duration.

    Selection: among Time: spans whose line is method-related, the one with the
    largest estimated duration; else the overall largest.  Replacement is
    strictly above the KB (max_h + 24 h), or the documented '45 days' constant
    under the UNSUPPORTED support gate.
    """
    raw_spans: List[Tuple[int, int, str, float, str]] = []
    for m in TIME_VALUE_RE.finditer(seed_text):
        start = m.start()
        end = m.end()
        val = m.group(1).strip()
        raw_spans.append((start, end, val, _estimate_hours(val), _step_number_of(seed_text, start)))
    if not raw_spans:
        return _op_clearing_time_fallback(seed_text, method, tier, kb)

    # Target a step whose window is labeling-free (KB time_excludes_labeling)
    # and, among those, prefer windows that mention clearing chemistry or the
    # stated method; then the largest estimated duration (tie -> earliest).
    scored: List[Tuple[Tuple[int, int, str, float, str], bool, bool]] = []
    for sp in raw_spans:
        ls = seed_text.rfind("\n", 0, sp[0]) + 1
        window = seed_text[max(0, ls - 200):sp[1]]
        labeling = _LABELING_CTX_RE.search(window) is not None
        clearing = _CLEARING_CTX_RE.search(window) is not None
        if method and method.lower() in window.lower():
            clearing = True
        scored.append((sp, labeling, clearing))
    nonlabel = [sp for sp, labeling, _c in scored if not labeling]
    pool0 = nonlabel if nonlabel else raw_spans
    clearing_pool = [sp for sp, _lab, cl in scored if sp in pool0 and cl]
    pool = clearing_pool if clearing_pool else pool0
    target = max(pool, key=lambda sp: (sp[3], -sp[0]))
    start, end, val, _hrs, step_no = target
    row, tier_ref = kb.time_row_for_tier(method, tier)
    if row is not None:
        repl_hours = float(row["clearing_time_max_h"]) + 24.0
        evidence = [kb.evidence_id_time(method, tier_ref)]
        fallback_used, fallback_note = False, ""
    else:
        repl_hours = 45.0 * 24.0  # documented unsupported-tier constant
        evidence = [kb.evidence_id_time_unsupported(method, tier)]
        fallback_used, fallback_note = True, "no (method, tier) row in time_kb.json; used documented '45 days' gate"
    repl = _replacement_in_style(val, repl_hours)
    return _OpResult(
        family=MutationFamily.CLEARING_TIME_OUT_OF_RANGE,
        relation=ExpectedRelation.HARD_FAIL,
        severity=SeverityLevel.CRITICAL,
        components=[ComponentId.S_TIME, ComponentId.COMPLETENESS],
        changed_field_paths=["protocol.steps[clearing].duration_hours"],
        edits=[(start, end, f"Time: {repl}")],
        surface_edits=[],
        evidence_ids=evidence,
        location=f"step {step_no or '?'} 'Time: {val}' -> 'Time: {repl}' (offset {start})",
        operator="clearing_time_out_of_range_v1.0",
        fallback_used=fallback_used,
        fallback_note=fallback_note,
    )


def _op_clearing_time_fallback(seed_text: str, method: str, tier: str, kb: KB) -> _OpResult:
    """Documented template fallback: append an out-of-range duration sentence."""
    insert = "（清理时间声明：45 days，超出该样本尺寸的支持范围）"
    # splice into the last byte so the edit target always exists
    pos = len(seed_text) - 1 if seed_text else 0
    repl = seed_text[pos] + insert if seed_text else insert
    edits = [(pos, pos + 1, repl)] if seed_text else [(0, len(insert), insert)]
    row, tier_ref = kb.time_row_for_tier(method, tier)
    if row is not None:
        evidence = [kb.evidence_id_time(method, tier_ref)]
    else:
        evidence = [kb.evidence_id_time_unsupported(method, tier)]
    return _OpResult(
        family=MutationFamily.CLEARING_TIME_OUT_OF_RANGE,
        relation=ExpectedRelation.HARD_FAIL,
        severity=SeverityLevel.CRITICAL,
        components=[ComponentId.S_TIME, ComponentId.COMPLETENESS],
        changed_field_paths=["protocol.steps[clearing].duration_hours"],
        edits=edits,
        surface_edits=[],
        evidence_ids=evidence,
        location="(fallback) appended out-of-range clearing-duration declaration",
        operator="clearing_time_out_of_range_v1.0",
        fallback_used=True,
        fallback_note="no 'Time:' spans found; appended a documented out-of-range clearing-time sentence",
    )


# ---------------------------------------------------------------------------
# Proposal assembly
# ---------------------------------------------------------------------------


def assemble_proposal(seed: SeedCandidate, res: _OpResult) -> MutationProposal:
    """Build a MutationProposal from an operator result (span + surface data)."""
    mutated, mut_spans = apply_edits(seed.response_text, res.edits)
    orig_spans = [
        TextSpan(path="response_text", start=s, end=e, text=seed.response_text[s:e])
        for (s, e, _nt) in res.edits
    ]
    mspans = [
        TextSpan(path="response_text", start=ms, end=me, text=nt)
        for (ms, me, nt) in mut_spans
    ]
    surface_edits = [
        SurfaceEdit(
            path="response_text",
            original_text=seed.response_text[s:e],
            mutated_text=nt,
            note=res.fallback_note if res.fallback_used else "",
        )
        for (s, e, nt) in res.surface_edits
    ]
    prop = MutationProposal(
        pair_id="MUT-000",  # placeholder; real id assigned by the deterministic sort
        seed_id=seed.seed_id,
        question_id=seed.question_id,
        scenario_type=seed.scenario_type,
        mutation_family=res.family,
        mutation_operator_version=MUTATION_OPERATOR_VERSION,
        changed_field_paths=list(res.changed_field_paths),
        original_text_spans=orig_spans,
        mutated_text_spans=mspans,
        surface_edits=surface_edits,
        expected_relation=res.relation,
        expected_affected_components=list(res.components),
        expected_location=res.location,
        expected_severity=res.severity,
        supporting_rule_or_evidence_ids=list(res.evidence_ids),
        review_status=ReviewStatus.PENDING_REVIEW,
        reviewer_ids=[],
        adjudication_status=AdjudicationStatus.PENDING,
        mutated_text=mutated,
        gold_note="",
        operator_fallback_used=res.fallback_used,
        operator_fallback_note=res.fallback_note,
    )
    prop.validate()
    return prop


def build_degrading_pair(seed: SeedCandidate, question: Dict[str, Any], family: MutationFamily, kb: KB) -> Tuple[MutationProposal, _OpResult]:
    """Build one DEGRADED/HARD_FAIL proposal for (seed, family)."""
    seed_text = seed.response_text
    qtext = question.get("question") or ""
    tier = (question.get("tissue_hierarchy_from_tissue_xlsx") or {}).get("tissue_tier_code") or ""
    targets = [t.get("marker_name") for t in question.get("marker_query_targets") or []]

    method: Optional[str] = None
    if family is MutationFamily.METHOD_FLUOROPHORE_CONFLICT or family is MutationFamily.SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT or family is MutationFamily.CLEARING_TIME_OUT_OF_RANGE:
        method = stated_method(seed_text)[0]

    if family is MutationFamily.REQUIRED_INFORMATION_OMISSION:
        res = op_required_omission(seed_text)
    elif family is MutationFamily.STEP_ORDER_OR_CHEMISTRY_CONFLICT:
        res = op_step_order(seed_text)
    elif family is MutationFamily.TARGET_MARKER_MISMATCH:
        res = op_target_marker(seed_text, targets)
    elif family is MutationFamily.METHOD_FLUOROPHORE_CONFLICT:
        if method is None:
            raise ValidationError(f"{seed.seed_id}: no stated method for fluorophore conflict")
        res = op_fluorophore_conflict(seed_text, method, kb)
    elif family is MutationFamily.SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT:
        if method is None:
            raise ValidationError(f"{seed.seed_id}: no stated method for sample-method scope")
        res = op_sample_method_scope(seed_text, qtext, method, tier, kb)
    elif family is MutationFamily.CLEARING_TIME_OUT_OF_RANGE:
        if method is None:
            raise ValidationError(f"{seed.seed_id}: no stated method for clearing-time")
        res = op_clearing_time(seed_text, method, tier, kb)
    else:  # pragma: no cover - defensive
        raise ValidationError(f"build_degrading_pair: unsupported family {family}")
    return assemble_proposal(seed, res), res


def assemble_equivalent_proposal(seed: SeedCandidate, control_family: MutationFamily, res: _OpResult) -> Tuple[MutationProposal, _OpResult]:
    """Turn an op_equivalent result into an EQUIVALENT proposal.

    ``control_family`` becomes the placeholder mutation_family (the matched
    control axis for the seed, documented in the build report).
    """
    res.family = control_family
    prop = assemble_proposal(seed, res)
    return prop, res


# ---------------------------------------------------------------------------
# run() + CLI
# ---------------------------------------------------------------------------


def _sort_key(prop: MutationProposal) -> Tuple[Any, ...]:
    eq = 0 if prop.expected_relation is ExpectedRelation.EQUIVALENT else 1
    fam = prop.mutation_family.value
    fam_idx = FAMILIES.index(fam) if fam in FAMILIES else 99
    return (prop.seed_id, eq, fam_idx, prop.pair_id)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def build(
    seed_path: str = DEFAULT_SEED_PATH,
    split_path: str = DEFAULT_SPLIT_PATH,
    question_path: Optional[str] = None,
    kb_root: str = KB_ROOT,
    role: str = "blind",
    proposals_path: str = DEFAULT_PROPOSALS_PATH,
    gold_path: str = DEFAULT_GOLD_PATH,
    build_report_path: str = DEFAULT_BUILD_REPORT,
) -> Dict[str, Any]:
    """Run the full build for the given split role.

    ``role="blind"`` builds all 24 seeds (72 proposals -- the delivered
    manifest).  ``role="development"`` builds the 16 dev seeds only (48
    proposals) and is used to exercise the split guard in tests.
    """
    if role not in ("development", "blind"):
        raise ValueError(f"unknown role {role!r}; expected 'development' or 'blind'")
    os.makedirs(os.path.dirname(proposals_path), exist_ok=True)
    os.makedirs(os.path.dirname(gold_path), exist_ok=True)
    os.makedirs(os.path.dirname(build_report_path), exist_ok=True)

    # role-routed seed loading: development role must use the dev-only manifest
    # (no blind rows); the full manifest is blind-only opt-in (finding #15).
    if role == "development" and seed_path == DEFAULT_SEED_PATH:
        seed_path = DEFAULT_DEV_SEED_PATH
    seeds = load_seed_candidates_role(seed_path, role, split_path)
    split = load_split_manifest(split_path)
    dev = set(split.development_seed_ids)
    blind = set(split.blind_seed_ids)
    for s in seeds:
        if s.seed_id not in dev | blind:
            raise ValidationError(f"seed {s.seed_id} not in split manifest ({split_path})")
    if role == "development":
        seeds = [s for s in seeds if s.seed_id in dev]
    seeds = sorted(seeds, key=lambda s: s.seed_id)
    all_seed_ids = sorted(dev | blind)

    if question_path is None:
        question_path = os.path.join(REPO_ROOT, QUESTION_FILE)
    questions = _load_questions_list(question_path)
    qid_missing = sorted({s.question_id for s in seeds} - set(questions))
    if qid_missing:
        raise ValidationError(f"question ids missing from {question_path}: {qid_missing}")

    # Dedicated, documented assignment maps (full plan always uses all 24).
    full_assignment = family_assignment(all_seed_ids)
    assignment = {sid: full_assignment[sid] for sid in (s.seed_id for s in seeds)}

    kb = KB(kb_root)
    pairs: List[Tuple[MutationProposal, _OpResult]] = []
    fallbacks: List[Dict[str, Any]] = []
    for seed in seeds:
        q = questions[seed.question_id]
        fams = assignment[seed.seed_id]
        res_eq = op_equivalent(seed.response_text)
        prop_eq, _ = assemble_equivalent_proposal(seed, MutationFamily(fams[0]), res_eq)
        pairs.append((prop_eq, res_eq))
        for fam_name in fams:
            fam = MutationFamily(fam_name)
            prop, res = build_degrading_pair(seed, q, fam, kb)
            pairs.append((prop, res))
            if res.fallback_used:
                fallbacks.append(
                    {
                        "seed_id": seed.seed_id,
                        "pair_family": fam.value,
                        "operator": res.operator,
                        "note": res.fallback_note,
                    }
                )

    # deterministic pair ids after a fixed sort.  The development-scoped build
    # prefixes its ids DEV-MUT-* so dev numbering can never collide with the
    # canonical MUT-* numbering of the blind-scope manifest (final-review
    # finding #2: the old dev manifest reused MUT-001..048 for different seeds,
    # so joins on pair_id silently mismatched).
    prefix = "DEV-" if role == "development" else ""
    pairs.sort(key=lambda pr: _sort_key(pr[0]))
    for idx, (prop, _res) in enumerate(pairs, start=1):
        prop.pair_id = f"{prefix}MUT-{idx:03d}"

    proposals = [prop for prop, _ in pairs]
    write_mutation_proposals(proposals_path, proposals)
    # empty human-reviewed gold stub (JSONL cannot hold comments; an empty file
    # means "no gold records approved yet")
    with open(gold_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("")

    summary = {
        "proposals_path": proposals_path,
        "gold_path": gold_path,
        "build_report_path": build_report_path,
        "role": role,
        "n_proposals": len(proposals),
        "n_equivalent": sum(1 for p in proposals if p.expected_relation is ExpectedRelation.EQUIVALENT),
        "n_degrading": sum(1 for p in proposals if p.expected_relation is not ExpectedRelation.EQUIVALENT),
        "fallbacks": fallbacks,
        "assignment": assignment,
        "full_assignment": full_assignment,
        "pairs": pairs,
        "sha256": {os.path.basename(proposals_path): _sha256_file(proposals_path)},
    }
    write_build_report(build_report_path, summary)
    return summary


def _load_questions_list(question_path: str) -> Dict[int, Dict[str, Any]]:
    data = _load_json_file(question_path)
    return {r["question_id"]: r for r in data}


def write_build_report(report_path: str, info: Dict[str, Any]) -> None:
    lines: List[str] = []
    if info.get("role") == "development":
        lines.append("# DEV_BUILD -- development-scoped proposal construction report (Task 2)")
        lines.append("")
        lines.append("Development-role build (16 seeds / 48 proposals): pair ids use the "
                     "`DEV-MUT-<NNN>` namespace so they can never collide with the canonical "
                     "`MUT-<NNN>` ids of the blind-scope manifest (72 pairs).")
    else:
        lines.append("# MUTATION_BUILD -- proposal construction report (Task 2)")
    lines.append("")
    lines.append(f"- proposals out : `{os.path.basename(info['proposals_path'])}`")
    lines.append(f"- gold stub out : `{os.path.basename(info['gold_path'])}` (empty file = no gold approved yet)")
    lines.append(f"- proposal count: {info['n_proposals']} (equivalent {info['n_equivalent']}, degrading {info['n_degrading']})")
    for base, digest in sorted(info.get("sha256", {}).items()):
        lines.append(f"- sha256 {base}: {digest}")
    lines.append("")
    lines.append("All operators: `mutation_operator_version = v1.0`, span-level edits on the")
    lines.append("seed `response_text`.  Every record is PENDING_REVIEW with empty reviewer_ids")
    lines.append("and adjudication_status = PENDING (the suite never fabricates APPROVED_GOLD).")
    lines.append("No ClearEval gold / expert labels / mutation labels / scorer thresholds are used.")
    lines.append("")
    lines.append("## Family -> seed assignment (seeded RNG, documented)")
    lines.append("")
    lines.append(
        "Algorithm: `FAMILIES` = the 6 families in canonical order; `rng = random.Random(20260817)`; "
        "`order = list(range(24)); rng.shuffle(order)`; the seed at shuffled index `i` receives "
        "`FAMILIES[(2*i) % 6]` and `FAMILIES[(2*i+1) % 6]`.  This is the only RNG consumption of the "
        "builder.  Each family is used exactly 8 times; every seed gets exactly 2 distinct families.  "
        "The EQUIVALENT variant of a seed carries the seed's first assigned family as its control "
        "axis (documented convention; the relation field is the semantic marker, not the placeholder "
        "family)."
    )
    lines.append("")
    lines.append("**EQUIVALENT control-axis coverage convention:** `FAMILIES[(2*i) % 6]` cycles i over "
                 "24 seeds, so only 3 of the 6 families ever appear as the first assigned family "
                 "(indices 0/2/4 -> REQUIRED_INFORMATION_OMISSION, TARGET_MARKER_MISMATCH, "
                 "SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT).  The `mutation_family` value on an EQUIVALENT "
                 "record is therefore a *placeholder control axis* only -- it is documented here and "
                 "is never treated as a semantic claim about the mutation (the relation field is the "
                 "semantic marker).")
    lines.append("")
    assignment = info["assignment"]
    lines.append("| seed_id | family 1 | family 2 |")
    lines.append("|---|---|---|")
    for sid in sorted(assignment):
        f1, f2 = assignment[sid]
        lines.append(f"| {sid} | {f1} | {f2} |")
    lines.append("")
    if info.get("full_assignment"):
        c = collections.Counter(f for v in info["full_assignment"].values() for f in v)
        lines.append("Degrading-family balance over the full 24-seed plan:")
        lines.append("")
        lines.append("| family | count |")
        lines.append("|---|---|")
        for fam in FAMILIES:
            lines.append(f"| {fam} | {c.get(fam, 0)} |")
        lines.append("")
    lines.append("## Operator expectations")
    lines.append("")
    lines.append("| family | relation | severity |")
    lines.append("|---|---|---|")
    lines.append("| EQUIVALENT | EQUIVALENT | NONE |")
    lines.append("| REQUIRED_INFORMATION_OMISSION | DEGRADED | MODERATE |")
    lines.append("| STEP_ORDER_OR_CHEMISTRY_CONFLICT | DEGRADED | MODERATE |")
    lines.append("| TARGET_MARKER_MISMATCH | DEGRADED | MODERATE |")
    lines.append("| METHOD_FLUOROPHORE_CONFLICT | DEGRADED | MODERATE |")
    lines.append("| SAMPLE_METHOD_OR_RI_SCOPE_CONFLICT | HARD_FAIL | CRITICAL |")
    lines.append("| CLEARING_TIME_OUT_OF_RANGE | HARD_FAIL | CRITICAL |")
    lines.append("")
    lines.append("## Fallbacks used")
    lines.append("")
    fbs = info.get("fallbacks", [])
    if not fbs:
        lines.append("None -- all degrading pairs used their primary span operator.")
    else:
        lines.append("| seed_id | family | operator | note |")
        lines.append("|---|---|---|---|")
        for fb in fbs:
            lines.append(f"| {fb['seed_id']} | {fb['pair_family']} | {fb['operator']} | {fb['note']} |")
    lines.append("")
    lines.append("## Per-pair operator log")
    lines.append("")
    lines.append("| pair_id | seed_id | family | relation | operator | spans |")
    lines.append("|---|---|---|---|---|---|")
    for prop, res in sorted(info_pairs(info), key=lambda pr: pr[0].pair_id):
        lines.append(
            f"| {prop.pair_id} | {prop.seed_id} | {prop.mutation_family.value} | "
            f"{prop.expected_relation.value} | {res.operator} | {len(prop.original_text_spans)} |"
        )
    lines.append("")
    with open(report_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))


def info_pairs(info: Dict[str, Any]) -> List[Tuple[MutationProposal, Any]]:
    return info["pairs"]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mutation_builder",
        description="ClearEval counterfactual-validity overlay: build the 72 mutation proposals.",
    )
    parser.add_argument("--seed-path", default=DEFAULT_SEED_PATH)
    parser.add_argument("--split-path", default=DEFAULT_SPLIT_PATH)
    parser.add_argument("--question-path", default=None)
    parser.add_argument("--kb-root", default=KB_ROOT)
    parser.add_argument("--role", choices=["development", "blind"], default="blind")
    parser.add_argument("--proposals", default=DEFAULT_PROPOSALS_PATH)
    parser.add_argument("--gold", default=DEFAULT_GOLD_PATH)
    parser.add_argument("--report", default=DEFAULT_BUILD_REPORT)
    args = parser.parse_args(argv)

    summary = build(
        seed_path=args.seed_path,
        split_path=args.split_path,
        question_path=args.question_path,
        kb_root=args.kb_root,
        role=args.role,
        proposals_path=args.proposals,
        gold_path=args.gold,
        build_report_path=args.report,
    )
    print(f"role       : {args.role}")
    print(f"proposals  : {summary['proposals_path']} ({summary['n_proposals']} records)")
    print(f"equivalent : {summary['n_equivalent']}  degrading: {summary['n_degrading']}")
    fb = summary["fallbacks"]
    print(f"fallbacks  : {len(fb)} " + ("" if not fb else "-> " + ", ".join(f["seed_id"] + ":" + f["pair_family"] for f in fb)))
    print(f"gold stub  : {summary['gold_path']}")
    print(f"report     : {summary['build_report_path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
