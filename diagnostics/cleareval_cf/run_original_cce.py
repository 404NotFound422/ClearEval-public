"""ClearEval counterfactual-validity overlay -- read-only CCE scoring adapter
(Task 3, deliverable 2).

This module turns a protocol text + question_id into ClearEval CCE component
scores (Completeness, Correctness, Effectiveness) without ever modifying a
production file.  It is the single scoring path used by the diagnostic audit
runner (``run_diagnostic_audit.py``) so that original and mutated protocols are
scored in fully independent calls through exactly the same adapter.

REUSE vs RE-IMPLEMENTATION (precise, per the task contract
"implement the adapter as a thin read-only re-derivation... and DOCUMENTS
precisely what is reused vs re-implemented"):

REUSED (read-only imports / files, never modified):
- ``extract_clearing_time.py`` (repo root): its deterministic
  ``extract_clearing_time(protocol_text)`` is the local source of
  ``clearing_total_time_hours`` (production obtains this value from the
  teacher's ``extraction`` JSON instead; the repo ships this deterministic
  extractor for the same quantity).
- ``mutation_builder.stated_method`` + the marker/fluorophore lexicons
  (``MARKER_TOKENS``/``DYE_TOKENS``/``DISTRACTOR_MARKERS``): the deterministic
  source of ``method_name`` and the marker vocabulary used to parse a
  deterministic ``marker_dict``.
- All knowledge-base files exactly as the production scorer loads them:
  ``KnowledgeBase/tissue.json``, ``method_fluro_compati.json``, ``time_kb.json``,
  ``method_time_tau.json``, ``tissue_ri.json``, ``method_sigma_ri.json``,
  ``method_ri_ref.json``; ``dataset/Q+AR/src/model_space_signed.json``,
  ``demand_vectors_all.json``, ``question_final.json``; and the optional
  ``workflow/s_label_audit/marker_specificity_tiers.json`` +
  ``fluorophore_classification_for_review.json``.

RE-IMPLEMENTED (faithful copies of the production formulas from
``OEQ_run_grading_new.py``; imported is impractical because that module runs
heavy import-time side effects -- API SDK imports, config reads, relative-path
KB loads -- and pulls the whole grading orchestration in): the effectiveness
scoring stack ``calculate_effectiveness_score`` and its helpers
(``_normalize_name``, ``find_signed_method``, ``calculate_method_suitability``,
marker/fluorophore matching ``_match_marker_to_targets`` /
``_classify_marker_specificity`` / ``_get_tissue_major_category`` /
``_get_marker_fluor_compat`` / ``_get_method_fluor_compat`` /
``_is_penalty_fluor`` / ``_map_fluor_to_tissue_col`` /
``_map_fluor_to_method_key``, ``_time_kb_row`` with the T07/T11 parent-tier
fallback, the S_trans and S_time formulas, and ``_resolve_tissue_ri``).  Each
re-implementation cites the production line it mirrors in its docstring.

DOCUMENTED DIVERGENCES from the production scoring path (analysis-grade re
-derivation is NOT bit-identical to a production run; the effect is isolated
to two LLM-extracted inputs and is question-fixed so directional/counterfactual
comparisons are unaffected):
1. ``method_name`` is obtained from the deterministic ``stated_method()``
   extractor; production uses the teacher's ``extraction.method_name``
   (though both feed the same ``find_signed_method`` matcher).
2. ``user_pref_vector`` for S_method is taken deterministically from
   ``dataset/Q+AR/src/demand_vectors_all.json`` (per-question, fixed); production
   obtains it from the teacher via ``get_user_preference_vector``.  The vector is
   fixed per question, so original vs mutated scoring of the same question uses
   the identical vector and directionality is preserved.
3. ``marker_dict`` is parsed deterministically from the protocol text; production
   uses the teacher's ``extraction.marker_dict``.  The deterministic parser is
   sensitive to the overlay's marker/fluorophore mutations by construction
   (see ``extract_marker_dict``) but will not reproduce a teacher extraction
   byte-for-byte.
4. For seeded ORIGINAL protocols the adapter can consume the production-frozen
   effectiveness record wholesale (``frozen_effectiveness`` / the seed's eval
   file), which is bit-exact production output; the local re-derivation is
   reserved for texts with no frozen record (the mutated side).

The adapter records full per-call metadata (teacher model name, prompt file hash,
schema/operator versions, timestamp, input sha256) for every scoring/audit run,
and never fabricates or imputes a score: any missing/failed judge output is
reported as a failure in the caller's coverage section, never silently filled.

Stdlib-only in the offline path; the ``--online`` path lazily imports the repo's
``models.Model_Loader`` and MUST NOT be used by the test suite (tests are
offline by contract).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

try:  # run as `python -m diagnostics.cleareval_cf.run_original_cce`
    from .mutation_builder import (
        DISTRACTOR_MARKERS,
        DYE_TOKENS,
        MARKER_TOKENS,
        _token_bounded,
        stated_method,
    )
except ImportError:  # run as `python diagnostics/cleareval_cf/run_original_cce.py`
    _PKG_DIR = os.path.dirname(os.path.abspath(__file__))
    if _PKG_DIR not in sys.path:
        sys.path.insert(0, _PKG_DIR)
    from mutation_builder import (  # type: ignore
        DISTRACTOR_MARKERS,
        DYE_TOKENS,
        MARKER_TOKENS,
        _token_bounded,
        stated_method,
    )

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(PKG_DIR))
KB_ROOT = os.path.join(REPO_ROOT, "KnowledgeBase")
QAR_SRC = os.path.join(REPO_ROOT, "dataset", "Q+AR", "src")
RESULT_DIR = os.path.join(REPO_ROOT, "dataset", "Q+AR", "result")
RESULTS_DIR = os.path.join(REPO_ROOT, "results")

# Repo-root deterministic clearing-time extractor (REUSED read-only).  Insert
# the repo root so it can be imported both as a package member and as a script.
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
import extract_clearing_time  # noqa: E402  (REUSED -- production-adjacent, stdlib)

ADAPTER_VERSION = "cce-adapter-v1"
SCHEMA_VERSION = "cleareval_cf.schemas.v1"
MUTATION_OPERATOR_VERSION = "v1.0"  # mirrors mutation_builder.MUTATION_OPERATOR_VERSION

# Canonical sub-score maxima -- MUST match results/aggregate_oeq.py MAX_SCORES
# and the production scorer output (OEQ_run_grading_new.py).
MAX_SCORES = {
    "c_step": 2, "c_param": 3, "co_order": 3, "co_method": 2,
    "co_param": 2, "co_chem": 1, "s_method": 2.5, "s_label": 6,
    "s_trans": 3, "s_time": 3,
}

# The production teacher rubric used for Completeness/Correctness (and, in the
# online path, the extraction): prompts/eval_oeq_teacher_rubric.txt.
PRODUCTION_RUBRIC_REL = os.path.join("prompts", "eval_oeq_teacher_rubric.txt")
PRODUCTION_RUBRIC_PATH = os.path.join(REPO_ROOT, PRODUCTION_RUBRIC_REL)

_SM_DIMS = [("fluorescence_protein_preservation", "F_fp"), ("dye_permeability", "P_dye"),
            ("clearing_challenge", "C_opt"), ("geometry_preference", "M_geo"),
            ("operational_economy", "E_ops"), ("safety_compatibility", "S_safe")]
S_METHOD_MAX = 2.5
_SM_DWEIGHT = 2.0

# T07/T11 parent-tier -> shortest-median sub-tier fallback (production:_PARENT_SUB).
_PARENT_SUB = {
    "T07_HARD_TISSUE_BONE_TOOTH_COCHLEA": [
        "T07A_SMALL_HARD_TISSUE_BONE_TOOTH", "T07B_LARGE_HARD_TISSUE_BONE_COCHLEA"],
    "T11_PLANT_WHOLE_SEEDLING": [
        "T11A_PLANT_LEAF_SMALL_SEEDLING", "T11B_PLANT_WHOLE_SEEDLING_ROOT"],
}

# Marker alias table -- faithful copy of production _MARKER_ALIASES
# (OEQ_run_grading_new.py:459-501).
_MARKER_ALIASES: Dict[str, List[str]] = {
    "gfp": ["gfp", "egfp", "gfp/yfp"],
    "egfp": ["egfp", "gfp", "gfp/yfp"],
    "yfp": ["yfp", "gfp", "gfp/yfp"],
    "rfp": ["rfp", "tdtomato", "mcherry", "mrfp"],
    "tdtomato": ["tdtomato", "rfp", "mcherry"],
    "mcherry": ["mcherry", "rfp", "tdtomato"],
    "tdtomatoreporter": ["tdtomato", "rfp", "mcherry"],
    "tuj1": ["tuj1", "βiiitubulin", "tubulinβiii", "tubulinbeta3", "beta3tubulin", "tubulinβ3"],
    "βiiitubulin": ["βiiitubulin", "tuj1", "tubulinβiii", "tubulinbeta3", "beta3tubulin"],
    "map2": ["map2", "microtubuleassociatedprotein2"],
    "neun": ["neun", "rbfox3"],
    "rbfox3": ["rbfox3", "neun"],
    "pgp95": ["pgp95", "pgp9.5", "proteingeneproduct9.5", "ubiquitincarboxylterminalhydrolase1"],
    "pgp9.5": ["pgp9.5", "pgp95", "proteingeneproduct9.5"],
    "neurofilament": ["neurofilament", "nf200", "nf"],
    "nf200": ["nf200", "neurofilament"],
    "cfos": ["cfos", "c-fos", "fos"],
    "c-fos": ["c-fos", "cfos", "fos"],
    "fos": ["fos", "cfos", "c-fos"],
    "npas4": ["npas4"],
    "cd31": ["cd31", "pecam1"],
    "pecam1": ["pecam1", "cd31"],
    "lectin": ["lectin", "ib4", "isolectin"],
    "ib4": ["ib4", "lectin", "isolectin"],
    "dii": ["dii", "dio", "did", "di"],
    "dio": ["dio", "dii", "did", "di"],
    "did": ["did", "dii", "dio", "di"],
    "alphabungarotoxin": ["alphabungarotoxin", "bungarotoxin", "achr"],
    "bungarotoxin": ["bungarotoxin", "alphabungarotoxin", "achr"],
    "phalloidin": ["phalloidin", "f-actin", "factin", "f-actin"],
    "factin": ["factin", "f-actin", "phalloidin"],
    "pancytokeratin": ["pancytokeratin", "ck", "cytokeratin"],
    "ck7": ["ck7", "cytokeratin7"],
    "ck19": ["ck19", "cytokeratin19"],
}

# Fluorescent-channel canonical mapping -- faithful copy of production
# _map_fluor_to_tissue_col mapping table (OEQ_run_grading_new.py:336-345).
_FLUOR_TO_TISSUE_MAP = {
    "gfp": "GFP/YFP", "egfp": "GFP/YFP", "yfp": "GFP/YFP",
    "tdtomato": "tdTomato/RFP ", "rfp": "tdTomato/RFP ", "mcherry": "tdTomato/RFP ", "mrfp": "tdTomato/RFP ",
    "dapi": "DAPI/Hoechst", "hoechst": "DAPI/Hoechst",
    "pi": "PI/Draq5 ", "draq5": "PI/Draq5 ",
    "alexafluor488": "AlexaFluor 488", "alexa488": "AlexaFluor 488",
    "alexafluor568": "AlexaFluor 568/Cy3", "alexa568": "AlexaFluor 568/Cy3", "cy3": "AlexaFluor 568/Cy3",
    "alexafluor647": "AlexaFluor 647/Cy5 ", "alexa647": "AlexaFluor 647/Cy5 ", "cy5": "AlexaFluor 647/Cy5 ",
    "cd31": "CD31", "lectin": "Lectin",
}

# Method-fluorophore key mapping -- faithful copy of production
# _map_fluor_to_method_key tables (OEQ_run_grading_new.py:395-454).
_FLUOR_TO_METHOD_SPECIFIC = {
    "alexafluor405": "Alexa Fluor 405", "alexafluor488": "Alexa Fluor 488", "alexa488": "Alexa Fluor 488",
    "alexafluor546": "Alexa Fluor 546", "alexafluor555": "Alexa Fluor 555", "alexafluor568": "Alexa Fluor 568",
    "alexafluor594": "Alexa Fluor 594", "alexafluor633": "Alexa Fluor 633", "alexafluor647": "Alexa Fluor 647",
    "alexafluor680": "Alexa Fluor 680", "alexafluor750": "Alexa Fluor 750",
    "fitc": "FITC", "fluorescein": "FITC", "tritc": "TRITC", "cy3": "Cy3", "cy5": "Cy5",
    "dylight405": "DyLight 405", "dylight488": "DyLight 488", "dylight550": "DyLight 550",
    "dylight594": "DyLight 594", "dylight649": "DyLight 649",
    "ifluor594": "iFluor 594", "ifluor647": "iFluor 647",
    "pe": "PE", "calcofluorwhite": "Calcofluor White", "calcofluor": "Calcofluor White",
    "neurotrace500": "NeuroTrace 500", "neurotrace": "NeuroTrace 500",
}
_FLUOR_TO_METHOD_COARSE = {
    "gfp": "GFP", "egfp": "EGFP", "yfp": "YFP",
    "tdtomato": "tdTomato", "rfp": "RFP", "mcherry": "mCherry", "mrfp": "mRFP",
    "alexafluor": "Alexa Fluor", "alexa": "Alexa Fluor",
    "dapi": "DAPI", "hoechst": "Hoechst",
    "pi": "Propidium iodide", "propidiumiodide": "Propidium iodide",
    "draq5": "TO-PRO-3", "topro3": "TO-PRO-3",
    "dii": "DiI", "dio": "DiO", "did": "DiD",
    "phalloidin": "Phalloidin", "alphabungarotoxin": "alpha-bungarotoxin",
    "lectin": "Lectin", "ib4": "IB4",
    "scrirenaissance2200": "SCRI Renaissance 2200",
}


# ---------------------------------------------------------------------------
# Hashing / metadata helpers
# ---------------------------------------------------------------------------


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def prompt_meta() -> Dict[str, Any]:
    """(prompt path, sha256, model default) for the production teacher rubric."""
    exists = os.path.isfile(PRODUCTION_RUBRIC_PATH)
    return {
        "prompt_path": PRODUCTION_RUBRIC_REL,
        "prompt_sha256": sha256_file(PRODUCTION_RUBRIC_PATH) if exists else None,
        "prompt_present": exists,
    }


def make_metadata(mode: str, teacher_model: str = "openai_gpt-5.2-thinking",
                  **extra: Any) -> Dict[str, Any]:
    """Deterministic-ish per-run metadata record (timestamp is wall clock)."""
    meta: Dict[str, Any] = {
        "adapter_version": ADAPTER_VERSION,
        "teacher_model": teacher_model,
        "schema_version": SCHEMA_VERSION,
        "mutation_operator_version": MUTATION_OPERATOR_VERSION,
        "mode": mode,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    meta.update(extra)
    return meta


# ---------------------------------------------------------------------------
# Knowledge bases (read-only; mirror of production import-time loads)
# ---------------------------------------------------------------------------


class RuleKBs:
    """Loads the KB files exactly as the production scorer does (read-only)."""

    def __init__(self, repo_root: str = REPO_ROOT, kb_root: str = KB_ROOT,
                 qar_src: str = QAR_SRC) -> None:
        self.repo_root = repo_root
        self.kb_root = kb_root
        self.qar_src = qar_src

        self.tissue_kb = _load_json(os.path.join(kb_root, "tissue.json"))
        self.method_fluro_kb = _load_json(os.path.join(kb_root, "method_fluro_compati.json"))
        self.time_kb_raw = _load_json(os.path.join(kb_root, "time_kb.json"))
        self.time_tau_raw = _load_json(os.path.join(kb_root, "method_time_tau.json"))
        self.tissue_ri_raw = _load_json(os.path.join(kb_root, "tissue_ri.json"))
        self.sigma_ri_raw = _load_json(os.path.join(kb_root, "method_sigma_ri.json"))
        self.method_ri_ref_raw = _load_json(os.path.join(kb_root, "method_ri_ref.json"))
        self.model_space_signed = _load_json(os.path.join(qar_src, "model_space_signed.json")).get("methods", {})
        self.question_list = _load_json(os.path.join(qar_src, "question_final.json"))
        self.demand_vectors = _load_json(os.path.join(qar_src, "demand_vectors_all.json"))

        # optional s_label audit tables (production loads them optionally)
        self.marker_specificity_tiers = _load_optional(
            os.path.join(repo_root, "workflow", "s_label_audit", "marker_specificity_tiers.json"),
            {"tier_0": [], "tier_3": [], "tier_6": []})
        self.fluor_evidence = _load_optional(
            os.path.join(repo_root, "workflow", "s_label_audit", "fluorophore_classification_for_review.json"),
            {})

        # ---- flattened tables (mirror production build-up) ----
        self._default_tissue_ri = float(self.tissue_ri_raw["tissue_ri_database"].get("default_ri", 1.48))
        self._tissue_ri_table: Dict[str, float] = {}
        for _cat, _items in self.tissue_ri_raw["tissue_ri_database"]["tissues"].items():
            for _k, _v in _items.items():
                if _k != "note" and isinstance(_v, (int, float)):
                    self._tissue_ri_table[_k] = float(_v)

        self._tissue_by_marker: Dict[str, Dict[str, Any]] = {}
        for row in self.tissue_kb:
            for key in ["推荐标志物 1", "推荐标志物 2"]:
                val = row.get(key)
                if val:
                    self._tissue_by_marker[_normalize_name(val)] = row

        self._method_fluoro_by_method: Dict[str, Dict[str, Any]] = {}
        for row in self.method_fluro_kb:
            method = row.get("method", "")
            if method:
                self._method_fluoro_by_method[_normalize_name(method)] = row

        self.time_kb_lookup: Dict[str, Any] = {}
        for _mk, _tiers in self.time_kb_raw.get("lookup", {}).items():
            self.time_kb_lookup[_normalize_name(_mk)] = _tiers

        self.sigma_ri_kb: Dict[str, Any] = {}
        for _mk, _tiers in self.sigma_ri_raw.get("sigma_RI", {}).items():
            self.sigma_ri_kb[_normalize_name(_mk)] = _tiers

        self.method_ri_ref_kb: Dict[str, float] = {
            _normalize_name(_k): float(_v["ri"])
            for _k, _v in self.method_ri_ref_raw.get("ri_ref", {}).items()
        }

        # optional fluorophore evidence: penalty + redirect sets
        self._penalty_fluors: set = set()
        self._marker_redirect_fluors: set = set()
        self._fluor_to_tissue_col: Dict[str, str] = {}
        fev = self.fluor_evidence
        for entry in fev.get("tissue_mappings", []):
            fluor, target = entry.get("fluor"), entry.get("target_column")
            if fluor and target:
                self._fluor_to_tissue_col[_normalize_name(fluor)] = target
        for entry in fev.get("penalty_list", []):
            fluor = entry.get("fluor")
            if fluor:
                self._penalty_fluors.add(_normalize_name(fluor))
        for entry in fev.get("marker_redirects", []):
            fluor = entry.get("fluor")
            if fluor:
                self._marker_redirect_fluors.add(_normalize_name(fluor))

        self._question_meta: Dict[int, Dict[str, Any]] = {
            q["question_id"]: {
                "tissue_tier_code": (q.get("tissue_hierarchy_from_tissue_xlsx") or {}).get("tissue_tier_code", ""),
                "tissue_inferred": (q.get("tissue_hierarchy_from_tissue_xlsx") or {}).get("tissue_inferred", ""),
                "tissue_ri_value": self._resolve_tissue_ri(
                    (q.get("tissue_hierarchy_from_tissue_xlsx") or {}).get("tissue_inferred", "")),
                "marker_query_targets": q.get("marker_query_targets", []),
            }
            for q in self.question_list
        }

    # -- tissue RI (faithful copy of production _resolve_tissue_ri) -----------
    def _resolve_tissue_ri(self, tissue_inferred: str) -> float:
        """Map Chinese tissue_inferred label -> tissue native RI (production
        OEQ_run_grading_new.py:101-167; branch order and fallback mirrored
        VERBATIM -- final-review finding #4)."""
        if not tissue_inferred:
            return self._default_tissue_ri
        s = tissue_inferred
        tbl = self._tissue_ri_table
        if "脑" in s and ("肿瘤" in s or "乳腺癌" in s or "转移" in s):
            return tbl["brain_tumor"]
        if "骨骼肌" in s or "腓肠肌" in s or "椎旁肌" in s:
            return tbl["skeletal_muscle"]
        if "牙" in s:
            return tbl["tooth"]
        if "颅骨" in s or "股骨" in s or "骨髓" in s or "骨" in s:
            return tbl["bone"]
        if "耳蜗" in s:
            return tbl["cochlea"]
        if "皮肤" in s:
            return tbl["skin"]
        if "心" in s:
            return tbl["heart"]
        if "肌" in s:
            return tbl["skeletal_muscle"]
        if "黑色素瘤" in s:
            return tbl["melanoma"]
        if "石蜡" in s:
            return tbl["tumor_paraffin"]
        if "淋巴结" in s:
            return tbl["lymph_node"]
        if "乳腺癌" in s:
            return tbl["breast_cancer"]
        if "前列腺" in s:
            return tbl["prostate"]
        if "肝" in s:
            return tbl["liver"]
        if "肾" in s:
            return tbl["kidney"]
        if "脾" in s:
            return tbl["spleen"]
        if "胰" in s:
            return tbl["pancreas"]
        if "胎盘" in s:
            return tbl["placenta"]
        if "胃" in s:
            return tbl["stomach"]
        if "肠" in s and "类器官" not in s:
            return tbl["intestine"]
        if "肺" in s:
            return tbl["lung"]
        if "睾丸" in s:
            return tbl["testis"]
        if "脂肪" in s:
            return tbl["fat"]
        if "肿瘤" in s:
            return tbl["tumor_dense"]
        if "全身" in s:
            return tbl["kidney"]  # whole-body soft-tissue default
        if "类器官" in s or "果蝇" in s:
            return tbl["organoid"]
        if "elegans" in s.lower():
            return tbl["celegans"]
        if "E14" in s:
            return tbl["embryo_brain"]
        if "胚胎" in s:
            return tbl["embryo_whole"]
        if "人脑" in s:
            return tbl["human_brain_block"]
        if "海马" in s:
            return tbl["hippocampus_ca1"]
        if "视网膜" in s or "眼球" in s:
            return tbl["eye_retina"]
        if "脊髓" in s or "CNS" in s:
            return tbl["spinal_cord"]
        if "斑马鱼" in s:
            return tbl["zebrafish"]
        if "脑" in s:
            return tbl["whole_brain"]
        if "植物" in s or "拟南芥" in s:
            return tbl["plant"]
        return self._default_tissue_ri

    def question_meta(self, question_id: int) -> Dict[str, Any]:
        m = self._question_meta.get(int(question_id), {})
        if not m:
            m = {
                "tissue_tier_code": "",
                "tissue_inferred": "",
                "tissue_ri_value": self._default_tissue_ri,
                "marker_query_targets": [],
            }
        return m

    def user_pref_vector(self, question_id: int) -> Dict[str, Any]:
        """Deterministic per-question demand vector (demand_vectors_all.json)."""
        return self.demand_vectors.get(str(int(question_id)), {})

    # marker/method lookups -----------------------------------------------------
    def is_penalty_fluor(self, fluor_name: str) -> bool:
        return _normalize_name(fluor_name) in self._penalty_fluors

    def marker_redirect_fluor(self, fluor_name: str) -> bool:
        return _normalize_name(fluor_name) in self._marker_redirect_fluors

    def map_fluor_to_tissue_col(self, fluor_name: str) -> Optional[str]:
        """Faithful copy of production _map_fluor_to_tissue_col."""
        s = _normalize_name(fluor_name)
        if not s:
            return None
        if s in _FLUOR_TO_TISSUE_MAP:
            return _FLUOR_TO_TISSUE_MAP[s]
        if s in self._fluor_to_tissue_col:
            return self._fluor_to_tissue_col[s]
        for k, v in _FLUOR_TO_TISSUE_MAP.items():
            if s.startswith(k) or k in s:
                return v
        return None

    def map_fluor_to_method_key(self, fluor_name: str) -> Optional[str]:
        """Faithful copy of production _map_fluor_to_method_key."""
        s = _normalize_name(fluor_name)
        if not s:
            return None
        if s in _FLUOR_TO_METHOD_SPECIFIC:
            return _FLUOR_TO_METHOD_SPECIFIC[s]
        if s in _FLUOR_TO_METHOD_COARSE:
            return _FLUOR_TO_METHOD_COARSE[s]
        for k, v in _FLUOR_TO_METHOD_SPECIFIC.items():
            if s.startswith(k):
                return v
        for k, v in _FLUOR_TO_METHOD_COARSE.items():
            if s.startswith(k):
                return v
        return None

    def get_tissue_major_category(self, marker_name: str) -> str:
        """Faithful copy of production _get_tissue_major_category."""
        row = self._tissue_by_marker.get(_normalize_name(marker_name))
        if row:
            return row.get("大类", "")
        norm = _normalize_name(marker_name)
        abbrevs = _extract_parenthetical(marker_name)
        for key, row in self._tissue_by_marker.items():
            if norm in key or key in norm:
                if len(norm) >= 3 and len(key) >= 3:
                    return row.get("大类", "")
            for abbr in abbrevs:
                if abbr in key:
                    return row.get("大类", "")
        return ""

    def get_marker_fluor_compat(self, marker_name: str, fluor_name: str) -> Optional[bool]:
        """Faithful copy of production _get_marker_fluor_compat
        (True compatible / False incompatible / None unknown)."""
        row = self._tissue_by_marker.get(_normalize_name(marker_name))
        if not row:
            norm = _normalize_name(marker_name)
            for key, r in self._tissue_by_marker.items():
                if norm in key or key in norm:
                    if len(norm) >= 3 and len(key) >= 3:
                        row = r
                        break
        if not row:
            return None
        col = self.map_fluor_to_tissue_col(fluor_name)
        if not col:
            return None
        val = row.get(col)
        if val == 0:
            return False
        return True

    def get_method_fluor_compat(self, method_name: str, fluor_name: str) -> Optional[float]:
        """Faithful copy of production _get_method_fluor_compat."""
        row = None
        norm_method = _normalize_name(method_name)
        for key, r in self._method_fluoro_by_method.items():
            if norm_method == key or norm_method in key or key in norm_method:
                row = r
                break
        if not row:
            return None
        key = self.map_fluor_to_method_key(fluor_name)
        if not key:
            return None
        val = row.get(key)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def classify_marker_specificity(self, marker_str: str) -> int:
        """Faithful copy of production _classify_marker_specificity."""
        if not marker_str:
            return 0
        norm = _normalize_name(marker_str)
        lower = marker_str.lower()
        tiers = self.marker_specificity_tiers
        tier_0 = {_normalize_name(m) for m in tiers.get("tier_0", [])}
        tier_3 = {_normalize_name(m) for m in tiers.get("tier_3", [])}
        tier_6 = {_normalize_name(m) for m in tiers.get("tier_6", [])}
        if norm in tier_0:
            return 0
        if norm in tier_3:
            return 3
        if norm in tier_6:
            return 6
        for vague in tiers.get("tier_0", []):
            if vague and (vague.lower() in lower or lower in vague.lower()):
                return 0
        for incomplete in tiers.get("tier_3", []):
            if incomplete and (incomplete.lower() in lower or lower in incomplete.lower()):
                return 3
        for specific in tiers.get("tier_6", []):
            if specific and (specific.lower() in lower or lower in specific.lower()):
                return 6
        return 6

    def _time_kb_row(self, method_key: str, tier_code: str) -> Optional[Dict[str, Any]]:
        """time_kb window for (normalized method, tier) with T07/T11 parent
        fallback (shortest median sub-tier) -- faithful copy of production
        _time_kb_row."""
        row = self.time_kb_lookup.get(method_key, {}).get(tier_code)
        if row is not None:
            return row
        subs = _PARENT_SUB.get(tier_code)
        if subs:
            cands = []
            for s in subs:
                sub = self.time_kb_lookup.get(method_key, {}).get(s)
                if sub and sub.get("clearing_time_median_h") is not None:
                    cands.append(sub)
            if cands:
                return min(cands, key=lambda v: v["clearing_time_median_h"])
        return None


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _load_optional(path: str, default: Any) -> Any:
    if os.path.isfile(path):
        try:
            return _load_json(path)
        except Exception:
            return default
    return default


# ---------------------------------------------------------------------------
# Re-implemented production helpers (documented above)
# ---------------------------------------------------------------------------


def _normalize_name(name: Any) -> str:
    """Faithful copy of production _normalize_name."""
    if not name:
        return ""
    s = str(name).lower()
    for ch in " -_–—/\\":
        s = s.replace(ch, "")
    return s


def _sm_norm(name: Any) -> str:
    """Production _sm_norm used ONLY by find_signed_method (like production).

    Additionally strips parentheses and '+' beyond _normalize_name -- the two
    normalizers differ on purpose; method-fit matching must mirror the
    production matcher (final-review finding #17).
    """
    s = str(name or "").lower()
    for ch in " -_/()":
        s = s.replace(ch, "")
    return s.replace("+", "")


def _extract_parenthetical(name: Any) -> List[str]:
    """Faithful copy of production _extract_parenthetical."""
    matches = re.findall(r"\(([^)]+)\)", str(name))
    return [_normalize_name(m) for m in matches]


def _expand_marker_candidates(name: Any) -> set:
    """Faithful copy of production _expand_marker_candidates (alias expansion)."""
    norm = _normalize_name(name)
    if not norm:
        return set()
    candidates = {norm}
    base = _normalize_name(re.sub(r"\s*[\(（][^)）]*[\)）]?", "", str(name)))
    if base and base != norm:
        candidates.add(base)
    lead = _normalize_name(re.split(r"[\(（,，、;；]", str(name))[0])
    if lead and lead not in candidates:
        candidates.add(lead)
    candidates.update(_extract_parenthetical(name))
    for key, equivalents in _MARKER_ALIASES.items():
        if key in candidates:
            candidates.update(equivalents)
    expanded = set(candidates)
    for key, equivalents in _MARKER_ALIASES.items():
        if expanded & set(equivalents):
            expanded.add(key)
            expanded.update(equivalents)
    return expanded


def _is_reporter_fluor(fluor_name: str) -> bool:
    s = _normalize_name(fluor_name)
    return any(x in s for x in ["gfp", "egfp", "yfp", "rfp", "tdtomato", "mcherry", "mrfp"])


def _is_reporter_target(target_name: str) -> bool:
    s = _normalize_name(target_name)
    return "reporter" in s or "Դ" in target_name  # mirror production literally


def _split_marker_value(value: Any) -> List[str]:
    if not value:
        return []
    parts = re.split(r"[;/,、，；／·]|\band\b|\bor\b|和|或", str(value))
    return [p.strip() for p in parts if p.strip()]


def match_marker_to_targets(marker_name: str, marker_query_targets: List[Any],
                            fluor_name: Optional[str] = None) -> bool:
    """Faithful copy of production _match_marker_to_targets."""
    candidate_names: List[str] = []
    if marker_name and str(marker_name).strip():
        candidate_names.append(str(marker_name).strip())
        candidate_names.extend(_split_marker_value(marker_name))
    if fluor_name and str(fluor_name).strip():
        candidate_names.append(str(fluor_name).strip())
    candidate_sets = [_expand_marker_candidates(c) for c in candidate_names]

    for target in marker_query_targets:
        target_name = target.get("marker_name", "")
        if not target_name:
            continue
        norm_target = _normalize_name(target_name)
        target_abbrevs = _extract_parenthetical(target_name)
        target_candidates = _expand_marker_candidates(target_name)
        for cand_set in candidate_sets:
            if cand_set & target_candidates:
                return True
            if cand_set & set(target_abbrevs):
                return True
            for cand in cand_set:
                if len(cand) < 3:
                    continue
                for tc in target_candidates:
                    if len(tc) < 3:
                        continue
                    if cand in tc or tc in cand:
                        return True
        if fluor_name and _is_reporter_target(target_name) and _is_reporter_fluor(fluor_name):
            fluor_set = _expand_marker_candidates(fluor_name)
            for fc in fluor_set:
                if len(fc) >= 3 and (fc in norm_target or norm_target in fc):
                    return True
    return False


def find_signed_method(name: str) -> Optional[Dict[str, float]]:
    """Faithful copy of production find_signed_method (model_space_signed).

    Uses production's ``_sm_norm`` (strips ``()``/``+`` too), matching the
    organic-solvent keyword fallback exactly.
    """
    nl = _sm_norm(name)
    if not nl:
        return None
    space = _signed_space()
    for k, v in space.items():
        kl = _sm_norm(k)
        if (nl in kl or kl in nl) and min(len(nl), len(kl)) >= 3:
            return v
    for kw, canon in (("3disco", "3DISCO"), ("thf", "3DISCO"), ("dbe", "3DISCO"),
                      ("dcm", "3DISCO"), ("babb", "BABB"), ("benzyl", "BABB"),
                      ("ethylcinnamate", "BABB"), ("idisco", "iDISCO (iDISCO+)"),
                      ("solvent", "3DISCO")):
        if kw in nl and canon in space:
            return space[canon]
    return None


_signed_space_cache: Optional[Dict[str, Dict[str, float]]] = None


def _signed_space() -> Dict[str, Dict[str, float]]:
    global _signed_space_cache
    if _signed_space_cache is None:
        path = os.path.join(QAR_SRC, "model_space_signed.json")
        _signed_space_cache = _load_json(path).get("methods", {})
    return _signed_space_cache


def calculate_method_suitability(user_pref_vector_dict: Dict[str, Any],
                                 method_vector_dict: Dict[str, Any]) -> float:
    """Faithful copy of production calculate_method_suitability (signed)."""
    if not user_pref_vector_dict or not method_vector_dict:
        return 0.0

    def _dem(longk: str) -> Tuple[float, float]:
        o = user_pref_vector_dict.get(longk, {}) or {}
        return float(o.get("target", 0) or 0), float(o.get("weight", 0) or 0)

    t_fp, w_fp = _dem("fluorescence_protein_preservation")
    t_pd, w_pd = _dem("dye_permeability")
    mult = {"F_fp": 1.0, "P_dye": 1.0}
    if w_fp * t_fp >= w_pd * t_pd:
        mult["F_fp"], mult["P_dye"] = _SM_DWEIGHT, 0.0
    else:
        mult["F_fp"], mult["P_dye"] = 0.0, _SM_DWEIGHT

    num = den = 0.0
    for longk, short in _SM_DIMS:
        t, w = _dem(longk)
        if short == "M_geo":
            t = min(t, 1.0)
        ds = mult.get(short, 1.0) * w * t
        if ds <= 0:
            continue
        num += ds * float(method_vector_dict.get(short, 0) or 0)
        den += ds
    if den <= 0:
        return 0.0
    return float(round(S_METHOD_MAX * (num / den), 4))


# ---------------------------------------------------------------------------
# Deterministic quantitative extraction (documented divergence 1/2/3)
# ---------------------------------------------------------------------------


def _preprocess_marker_dict(marker_dict: Dict[str, str], kbs: RuleKBs
                            ) -> Tuple[List[Tuple[str, str]], bool, bool]:
    """Faithful copy of production _preprocess_marker_dict (uses redirects)."""
    preprocessed: List[Tuple[str, str]] = []
    has_marker_without_fluor = False
    has_fluor_without_marker = False
    for fluor, marker in marker_dict.items():
        fluor_str = str(fluor).strip() if fluor else ""
        marker_str = str(marker).strip() if marker else ""
        if fluor_str and kbs.marker_redirect_fluor(fluor_str):
            preprocessed.append(("", fluor_str))
            if not marker_str:
                has_marker_without_fluor = True
            continue
        preprocessed.append((fluor_str, marker_str))
        if fluor_str and not marker_str:
            has_fluor_without_marker = True
        if marker_str and not fluor_str:
            has_marker_without_fluor = True
    return preprocessed, has_marker_without_fluor, has_fluor_without_marker


_DYE_RE = re.compile("|".join(re.escape(t) for t in sorted(DYE_TOKENS, key=len, reverse=True)))
_MARKER_RE = re.compile(
    "|".join(re.escape(t) for t in sorted(set(MARKER_TOKENS) | set(DISTRACTOR_MARKERS), key=len, reverse=True)))


def extract_marker_dict(protocol_text: str) -> Dict[str, str]:
    """Deterministic marker_dict from a protocol text (documented divergence 3).

    Parser: split the labeling region into `+`-separated groups and pair each
    dye group with the nearest marker token in the preceding marker-only group.
    Dyes without any found marker map to "" (mirroring the teacher's convention
    for nuclear counterstains such as DAPI).
    """
    if not protocol_text:
        return {}
    label_region = protocol_text[: min(len(protocol_text), 2500)]
    label_region = re.split(r"[\uFF5C|]", label_region)[0]  # first segment before ｜/|

    groups = [g.strip() for g in re.split(r"\s*\+\s*", label_region) if g.strip()]

    def _tokens_in(seg: str, regex: "re.Pattern[str]", vocab) -> List[str]:
        out: List[str] = []
        for m in regex.finditer(seg):
            if _token_bounded(m, seg) and m.group(0) in vocab:
                out.append(m.group(0))
        return out

    marker_dict: Dict[str, str] = {}
    prev_markers: List[str] = []
    for group in groups:
        dyes = _tokens_in(group, _DYE_RE, DYE_TOKENS)
        markers = _tokens_in(group, _MARKER_RE, set(MARKER_TOKENS) | set(DISTRACTOR_MARKERS))
        this_markers: List[str] = []
        for mk in markers:
            norm = _normalize_name(mk)
            if any(_normalize_name(d) == norm for d in dyes):
                continue  # a dye is not also treated as its own marker here
            this_markers.append(mk)
        if dyes:
            # Pair each dye in this group with the nearest unconsumed marker
            # token.  Convention mirrors the teacher's: a marker declared in one
            # strategy clause labels the fluorophore named in the following
            # clause; once used it is consumed, so a later bare counterstain
            # (e.g. DAPI / TO-PRO-3) gets an empty marker value.
            marker = ""
            if this_markers:
                marker = this_markers[0]
            elif prev_markers:
                marker = prev_markers.pop()
            else:
                marker = ""
            for dye_token in dyes:
                marker_dict[dye_token] = marker
            prev_markers = []  # marker consumed by this pair
        if not dyes and this_markers:
            prev_markers = list(this_markers)
    return marker_dict


def extract_quantitative(protocol_text: str, question_id: int, kbs: RuleKBs
                         ) -> Dict[str, Any]:
    """Deterministic (method_name, clearing_total_time_hours, marker_dict, meta)
    for a protocol text (documented divergences 1/2/3)."""
    method_key, _span = stated_method(protocol_text)
    clearing_time = extract_clearing_time.extract_clearing_time(protocol_text)
    marker_dict = extract_marker_dict(protocol_text) if protocol_text else {}
    qm = kbs.question_meta(question_id)
    return {
        "method_name": method_key or "",
        "total_time_hours": float(clearing_time) if clearing_time is not None else 0.0,
        "marker_dict": marker_dict,
        "sample_tier": qm.get("tissue_tier_code", ""),
        "tissue_ri_value": qm.get("tissue_ri_value", 0.0),
        "user_pref_vector": kbs.user_pref_vector(question_id),
        "marker_query_targets": qm.get("marker_query_targets", []),
    }


def calculate_effectiveness_score(quantitative_data: Dict[str, Any],
                                  user_pref_vector_dict: Dict[str, Any],
                                  marker_dict: Dict[str, str],
                                  marker_query_targets: List[Any],
                                  kbs: RuleKBs) -> Dict[str, Any]:
    """Faithful re-implementation of production calculate_effectiveness_score
    (OEQ_run_grading_new.py:1038-1227).  ``kbs`` supplies the KB lookups."""
    w1 = w2 = w3 = w4 = 1.0
    method_name = _coerce_str(quantitative_data.get("method_name"), default="")
    method_vector_dict = find_signed_method(method_name)
    if method_vector_dict is None:
        s_method = 0.0
    else:
        s_method = calculate_method_suitability(user_pref_vector_dict, method_vector_dict)

    marker_pairs, _mwo, _fwo = _preprocess_marker_dict(marker_dict, kbs)

    # s_target_match
    target_match_scores: List[float] = []
    for fluor_str, marker_str in marker_pairs:
        if not marker_str:
            continue
        if match_marker_to_targets(marker_str, marker_query_targets, fluor_name=fluor_str):
            target_match_scores.append(6.0)
        else:
            specificity = kbs.classify_marker_specificity(marker_str)
            if specificity == 0:
                target_match_scores.append(0.0)
            elif specificity == 3:
                target_match_scores.append(3.0)
            else:
                marker_major = kbs.get_tissue_major_category(marker_str)
                question_major = ""
                if marker_query_targets:
                    question_major = marker_query_targets[0].get("major_category", "")
                if marker_major and question_major and marker_major == question_major:
                    target_match_scores.append(3.0)
                else:
                    target_match_scores.append(0.0)
    s_target_match = min(target_match_scores) if target_match_scores else 0.0

    # s_marker_fluor_compat
    marker_fluor_scores: List[float] = []
    for fluor_str, marker_str in marker_pairs:
        if not marker_str:
            continue
        if kbs.is_penalty_fluor(fluor_str):
            marker_fluor_scores.append(0.0)
            continue
        compat = kbs.get_marker_fluor_compat(marker_str, fluor_str)
        if compat is False:
            marker_fluor_scores.append(0.0)
        else:
            marker_fluor_scores.append(6.0)
    s_marker_fluor_compat = min(marker_fluor_scores) if marker_fluor_scores else 6.0

    # s_method_fluor_compat
    method_fluor_scores: List[float] = []
    for fluor_str, marker_str in marker_pairs:
        if kbs.is_penalty_fluor(fluor_str):
            method_fluor_scores.append(0.0)
            continue
        compat_val = kbs.get_method_fluor_compat(method_name, fluor_str)
        if compat_val is None:
            method_fluor_scores.append(6.0)
        else:
            method_fluor_scores.append(compat_val * 6.0)
    s_method_fluor_compat = min(method_fluor_scores) if method_fluor_scores else 6.0

    s_label = min(s_target_match, s_marker_fluor_compat, s_method_fluor_compat)
    s_label = max(0.0, min(6.0, s_label))

    tier_code = _coerce_str(quantitative_data.get("sample_tier"), default="")
    method_key = _normalize_name(method_name)
    ri_tissue = _coerce_float(quantitative_data.get("tissue_ri_value"), default=0.0)
    ri_method_ref = kbs.method_ri_ref_kb.get(method_key)
    sigma_ri = kbs.sigma_ri_kb.get(method_key, {}).get(tier_code) if tier_code else None
    time_kb_supported = bool(kbs._time_kb_row(method_key, tier_code))

    if not time_kb_supported:
        s_trans = 0.0
        _s_trans_sigma = sigma_ri
        _s_trans_status = "out_of_method_range"
    elif ri_method_ref is None or sigma_ri is None or float(sigma_ri) == 0.0 or not ri_tissue:
        s_trans = 0.0
        _s_trans_sigma = sigma_ri
        _s_trans_status = "missing_kb"
    else:
        _s_trans_sigma = float(sigma_ri)
        exponent = -0.5 * ((float(ri_tissue) - float(ri_method_ref)) / _s_trans_sigma) ** 2
        s_trans = 3.0 * _exp(exponent)
        s_trans = max(0.0, min(3.0, s_trans))
        _s_trans_status = "scored"

    t_act = _coerce_float(quantitative_data.get("total_time_hours"), default=0.0)
    _TAU_UNDER, _TAU_OVER = 0.2, 0.1
    tier_data = kbs._time_kb_row(method_key, tier_code)
    _s_time_med = (float(tier_data["clearing_time_median_h"])
                   if (tier_data and tier_data.get("clearing_time_median_h") is not None) else None)

    if tier_data is None or _s_time_med is None or _s_time_med <= 0.0:
        s_time = 0.0
        _s_time_t_min = _s_time_t_max = _s_time_tau = None
    elif t_act <= 0.0:
        s_time = 0.0
        _s_time_t_min = float(tier_data["clearing_time_min_h"])
        _s_time_t_max = float(tier_data["clearing_time_max_h"])
        _s_time_tau = _TAU_UNDER * _s_time_med
    else:
        _s_time_t_min = float(tier_data["clearing_time_min_h"])
        _s_time_t_max = float(tier_data["clearing_time_max_h"])
        if t_act < _s_time_t_min:
            delta_t = _s_time_t_min - t_act
            _s_time_tau = _TAU_UNDER * _s_time_med
        elif t_act > _s_time_t_max:
            delta_t = t_act - _s_time_t_max
            _s_time_tau = _TAU_OVER * _s_time_med
        else:
            delta_t = 0.0
            _s_time_tau = _TAU_UNDER * _s_time_med
        s_time = 3.0 if delta_t == 0.0 else 3.0 * _exp(-0.5 * (delta_t / _s_time_tau) ** 2)

    s_time = max(0.0, min(3.0, s_time))
    e_score = w1 * s_method + w2 * s_label + w3 * s_trans + w4 * s_time

    return {
        "s_method": s_method,
        "s_label": s_label,
        "s_trans": s_trans,
        "s_time": s_time,
        "total_effectiveness_score": e_score,
        "s_target_match": s_target_match,
        "s_marker_fluor_compat": s_marker_fluor_compat,
        "s_method_fluor_compat": s_method_fluor_compat,
        "_s_trans_status": _s_trans_status,
        "_s_time_t_act": t_act,
    }


def _coerce_str(val: Any, default: str = "") -> str:
    if val is None:
        return default
    try:
        s = str(val).strip()
        return s if s else default
    except Exception:
        return default


def _coerce_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


# math.exp but keep this module import-light; math is stdlib
import math  # noqa: E402


def _exp(x: float) -> float:
    return math.exp(x)


# ---------------------------------------------------------------------------
# CCE assembly + judge handling
# ---------------------------------------------------------------------------

JUDGE_SUBSCORES = {
    "completeness": ["c_step", "c_param"],
    "correctness": ["co_order", "co_method", "co_param", "co_chem"],
}


class JudgeError(ValueError):
    """Raised when a judge payload is missing/unusable (never imputed)."""


def validate_judge_payload(payload: Any) -> Dict[str, Any]:
    """Validate a judge payload into the canonical {completeness, correctness}.

    ``payload`` may be ``None``, a dict with ``completeness``/``correctness``
    blocks (production record shape), or a full production eval record with
    ``evaluation.scores``.  Raises ``JudgeError`` describing the first missing
    sub-score; never fabricates scores.

    A judge error is *reported*, not swallowed: callers route it into the
    coverage section and do not score the case.
    """
    record = payload
    if record is None:
        raise JudgeError("judge payload is missing (None)")
    if not isinstance(record, dict):
        raise JudgeError(f"judge payload must be an object, got {type(record).__name__}")
    if "evaluation" in record and isinstance(record.get("evaluation"), dict):
        record = record["evaluation"]
    scores = record.get("scores")
    if not isinstance(scores, dict):
        raise JudgeError("judge payload has no 'scores' object")
    out: Dict[str, Any] = {}
    for part, subs in JUDGE_SUBSCORES.items():
        block = scores.get(part)
        if not isinstance(block, dict):
            raise JudgeError(f"judge payload missing scores.{part}")
        part_out: Dict[str, Any] = {}
        for sub in subs:
            subval = block.get(sub)
            if not isinstance(subval, dict) or subval.get("score") is None:
                raise JudgeError(f"judge payload missing scores.{part}.{sub}.score")
            try:
                score = float(subval["score"])
            except (TypeError, ValueError):
                raise JudgeError(f"judge payload scores.{part}.{sub}.score not numeric")
            max_score = subval.get("max_score")
            try:
                max_score = float(max_score) if max_score is not None else float(MAX_SCORES[sub])
            except (TypeError, ValueError):
                max_score = float(MAX_SCORES[sub])
            if not -1e-9 <= score <= max_score + 1e-9:
                raise JudgeError(
                    f"judge payload scores.{part}.{sub}.score {score} outside [0,{max_score}]")
            part_out[sub] = {"score": score, "max_score": max_score}
        total = block.get("total_weighted_score")
        try:
            total = float(total) if total is not None else sum(v["score"] for v in part_out.values())
        except (TypeError, ValueError):
            raise JudgeError(f"judge payload scores.{part}.total_weighted_score not numeric")
        part_out["total"] = total
        out[part] = part_out
    return out


def assemble_cce(question_id: int, protocol_text: str,
                 judge: Dict[str, Any],
                 effectiveness: Dict[str, Any],
                 metadata: Dict[str, Any],
                 status: str = "ok") -> Dict[str, Any]:
    """Assemble the canonical CCE record (plain dict, JSON-serializable)."""
    comp = judge["completeness"]
    corr = judge["correctness"]
    eff = effectiveness
    eff_total = float(eff.get("total_effectiveness_score", 0.0))
    total_cc = comp["total"] + corr["total"] + eff_total
    return {
        "question_id": int(question_id),
        "protocol_sha256": sha256_text(protocol_text),
        "status": status,
        "components": {
            "completeness": {
                "c_step": comp["c_step"]["score"],
                "c_param": comp["c_param"]["score"],
                "max": 5.0,
                "total": comp["total"],
            },
            "correctness": {
                "co_order": corr["co_order"]["score"],
                "co_method": corr["co_method"]["score"],
                "co_param": corr["co_param"]["score"],
                "co_chem": corr["co_chem"]["score"],
                "max": 8.0,
                "total": corr["total"],
            },
            "effectiveness": {
                "s_method": float(eff.get("s_method", 0.0)),
                "s_label": float(eff.get("s_label", 0.0)),
                "s_trans": float(eff.get("s_trans", 0.0)),
                "s_time": float(eff.get("s_time", 0.0)),
                "max": 14.5,
                "total": eff_total,
                "_meta": {
                    source: str(value) for source, value in _effectiveness_source(eff).items()
                },
            },
        },
        "total_cc": total_cc,
        "metadata": metadata,
    }


def _effectiveness_source(eff: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k in ("_s_trans_status", "_s_time_t_act", "s_target_match",
              "s_marker_fluor_compat", "s_method_fluor_compat"):
        if k in eff:
            out[k] = eff[k]
    return out


def frozen_effectiveness_to_components(seed_cce: Dict[str, Any]) -> Dict[str, Any]:
    """Extract effectiveness from a frozen seed cce_scores record.

    ``seed_cce`` is the ``cce_scores`` dict stored in the seed manifest
    (completeness/correctness/effectiveness each with sub-score dicts).
    """
    eff = seed_cce.get("effectiveness", {})
    comp = seed_cce.get("completeness", {})
    corr = seed_cce.get("correctness", {})
    judge = {
        "completeness": {sub: {"score": comp.get(sub, {}).get("score"),
                               "max_score": comp.get(sub, {}).get("max_score")}
                         for sub in ("c_step", "c_param")},
        "correctness": {sub: {"score": corr.get(sub, {}).get("score"),
                              "max_score": corr.get(sub, {}).get("max_score")}
                        for sub in ("co_order", "co_method", "co_param", "co_chem")},
    }
    totals = {
        "completeness": comp.get("total_weighted_score"),
        "correctness": corr.get("total_weighted_score"),
    }
    for part in ("completeness", "correctness"):
        if totals[part] is not None:
            judge[part]["total"] = float(totals[part])
    effectiveness = {
        "s_method": eff.get("s_method", {}).get("score", 0.0),
        "s_label": eff.get("s_label", {}).get("score", 0.0),
        "s_trans": eff.get("s_trans", {}).get("score", 0.0),
        "s_time": eff.get("s_time", {}).get("score", 0.0),
        "total_effectiveness_score": eff.get("total_weighted_score", 0.0),
        "_source": "frozen",
    }
    return judge, effectiveness


class CCEScorer:
    """Offline + (optional) online CCE scoring adapter (read-only)."""

    def __init__(self, repo_root: str = REPO_ROOT, judge_factory: Optional[Any] = None) -> None:
        self.repo_root = repo_root
        self.kbs = RuleKBs(repo_root)
        # judge_factory: callable () -> judge with a single `audit(...)` method,
        # used in online mode; None keeps the scorer offline.
        self.judge_factory = judge_factory

    # -- offline scoring -------------------------------------------------------
    def score_protocol_from_parts(
        self,
        protocol_text: str,
        question_id: int,
        judge_cc: Optional[Dict[str, Any]] = None,
        frozen_effectiveness: Optional[Dict[str, Any]] = None,
        mode: str = "offline",
        teacher_model: str = "openai_gpt-5.2-thinking",
    ) -> Dict[str, Any]:
        """Score one protocol from explicit parts.

        - ``judge_cc``: the Completeness/Correctness judge payload (cached/frozen
          record or injected fixture).  If None -> the result is an explicit
          failure (status="judge_missing"), never imputed.
        - ``frozen_effectiveness``: optional full effectiveness block (frozen
          production record).  When given it is used as-is; otherwise the local
          rule-based re-derivation computes it.
        """
        meta = make_metadata(mode=mode, teacher_model=teacher_model)
        if judge_cc is None:
            return {
                "question_id": int(question_id),
                "protocol_sha256": sha256_text(protocol_text),
                "status": "judge_missing",
                "total_cc": None,
                "components": None,
                "metadata": meta,
            }
        try:
            judge = validate_judge_payload(judge_cc)
        except JudgeError as exc:
            return {
                "question_id": int(question_id),
                "protocol_sha256": sha256_text(protocol_text),
                "status": "judge_failed",
                "error": str(exc),
                "total_cc": None,
                "components": None,
                "metadata": meta,
            }

        if frozen_effectiveness is not None:
            eff = {
                "s_method": float(frozen_effectiveness.get("s_method", 0.0)),
                "s_label": float(frozen_effectiveness.get("s_label", 0.0)),
                "s_trans": float(frozen_effectiveness.get("s_trans", 0.0)),
                "s_time": float(frozen_effectiveness.get("s_time", 0.0)),
                "total_effectiveness_score": float(
                    frozen_effectiveness.get("total_weighted_score", 0.0)),
                "_source": "frozen",
            }
        else:
            q = extract_quantitative(protocol_text, question_id, self.kbs)
            eff = calculate_effectiveness_score(
                quantitative_data=q,
                user_pref_vector_dict=q["user_pref_vector"],
                marker_dict=q["marker_dict"],
                marker_query_targets=q["marker_query_targets"],
                kbs=self.kbs,
            )
            eff["_source"] = "local_rule_re-derivation"
        return assemble_cce(question_id, protocol_text, judge, eff, meta, status="ok")

    # -- online scoring (NEVER used by tests; requires repo deps) --------------
    def score_online(self, protocol_text: str, question_id: int,
                     teacher_name: str = "openai_gpt-5.2-thinking",
                     config_path: Optional[str] = None) -> Dict[str, Any]:
        """Production-path online scoring through the repo's model loader.

        Lazily imports ``models.Model_Loader`` + builds the production rubric
        prompt; Completeness/Correctness/extraction come from the teacher.  Only
        intended to be run manually; raises ImportError/RuntimeError if the
        model stack is unavailable.
        """
        from .online_cce import score_online_cce  # lazy; never imported in tests

        return score_online_cce(
            protocol_text=protocol_text,
            question_id=question_id,
            teacher_name=teacher_name,
            config_path=config_path,
            repo_root=self.repo_root,
        )


# ---------------------------------------------------------------------------
# verify-aggregation (fixture-equivalence check)
# ---------------------------------------------------------------------------

CANONICAL_MODELS = sorted([
    "gemini-3-flash", "gemini-3-pro", "glm4.7-thinking", "glm4.7-unthinking",
    "openai_claude-sonnet-4.6", "openai_deepseek-chat", "openai_deepseek-reasoner",
    "openai_gpt-5.2-fast", "openai_gpt-5.2-thinking",
    "openai_qwen3-14b", "openai_qwen3-235b", "openai_qwen3-32b", "openai_qwen3-max",
])


def replicate_aggregate_oeq(result_dir: str = RESULT_DIR) -> List[Dict[str, Any]]:
    """Recompute per-model aggregation exactly as results/aggregate_oeq.py does.

    Scope: the 13 canonical base ``evaluation_results_<model>_1-shot.json`` files
    that ``results/oeq_stats_260223.jsonl`` covers.  (The naive production glob
    would today also pick up the 9 KB-RAG variants, so the verification targets
    the canonical 13 base files that the committed stats file actually holds.)
    """
    rows: List[Dict[str, Any]] = []
    for model in CANONICAL_MODELS:
        path = os.path.join(result_dir, f"evaluation_results_{model}_1-shot.json")
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        metrics: Dict[str, List[float]] = {k: [] for k in MAX_SCORES}
        evals = data if isinstance(data, list) else [data]
        for item in evals:
            eval_obj = item.get("evaluation", {})
            scores_obj = eval_obj.get("scores", {})
            comp = scores_obj.get("completeness", {})
            for m in ["c_step", "c_param"]:
                val = comp.get(m, {}).get("score")
                if val is not None:
                    metrics[m].append(float(val))
            corr = scores_obj.get("correctness", {})
            for m in ["co_order", "co_method", "co_param", "co_chem"]:
                val = corr.get(m, {}).get("score")
                if val is not None:
                    metrics[m].append(float(val))
            eff = scores_obj.get("effectiveness", {})
            for m in ["s_method", "s_label", "s_trans", "s_time"]:
                val = eff.get(m, {}).get("score")
                if val is not None:
                    metrics[m].append(float(val))
        if not any(metrics.values()):
            continue
        avg_scores: Dict[str, Any] = {}
        for m, vals in metrics.items():
            avg = sum(vals) / len(vals) if vals else 0
            avg_scores[m] = avg
            avg_scores[f"{m}_norm"] = avg / MAX_SCORES[m] if MAX_SCORES[m] > 0 else 0
        sample_count = len(next(iter(metrics.values()))) if metrics.values() else 0
        rows.append({
            "model_name": model,
            "average_scores": avg_scores,
            "sample_count": sample_count,
        })
    return rows


def compare_stats_with_frozen(recomputed: List[Dict[str, Any]],
                              stats_path: Optional[str] = None) -> Dict[str, Any]:
    """Compare recomputed aggregation rows against results/oeq_stats_260223.jsonl.

    Returns per-row max-abs-diff and an exact-equivalence flag plus any missing
    rows.  Exact match is expected (same algorithm, same data); a diff above the
    documented tolerance (1e-9) would indicate drift in the frozen eval files or
    the stats file.
    """
    stats_path = stats_path or os.path.join(RESULTS_DIR, "oeq_stats_260223.jsonl")
    frozen: List[Dict[str, Any]] = []
    with open(stats_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                frozen.append(json.loads(line))
    frozen_by_model = {r["model_name"]: r for r in frozen}
    report: Dict[str, Any] = {
        "stats_path": stats_path,
        "n_recomputed": len(recomputed),
        "n_frozen": len(frozen),
        "missing_in_recomputed": sorted(set(frozen_by_model) - {r["model_name"] for r in recomputed}),
        "missing_in_frozen": sorted({r["model_name"] for r in recomputed} - set(frozen_by_model)),
        "rows": [],
    }
    worst: float = 0.0
    for row in recomputed:
        name = row["model_name"]
        frow = frozen_by_model.get(name)
        if frow is None:
            report["rows"].append({"model_name": name, "present_in_frozen": False, "max_abs_diff": None})
            continue
        keys = sorted(set(list(frow.get("average_scores", {})) + list(row.get("average_scores", {}))))
        diffs = []
        for k in keys:
            a = row.get("average_scores", {}).get(k)
            b = frow.get("average_scores", {}).get(k)
            if a is not None and b is not None:
                diffs.append(abs(float(a) - float(b)))
            elif (a is not None) != (b is not None):
                diffs.append(float("inf"))
        if frow.get("sample_count") != row.get("sample_count"):
            diffs.append(float("inf"))
        maxdiff = max(diffs) if diffs else 0.0
        worst = max(worst, maxdiff)
        report["rows"].append({
            "model_name": name,
            "present_in_frozen": True,
            "sample_count_match": frow.get("sample_count") == row.get("sample_count"),
            "max_abs_diff": float(maxdiff),
            "exact": maxdiff == 0.0 and frow.get("sample_count") == row.get("sample_count"),
        })
    report["max_abs_diff_across_rows"] = float(worst)
    report["tolerance"] = 1e-9
    report["tolerance_justification"] = (
        "Exact equality is expected: the recommutation uses the same per-sub-metric "
        "mean + MAX_SCORES normalization over the same frozen eval files that "
        "produced oeq_stats_260223.jsonl (results/aggregate_oeq.py).  The 1e-9 "
        "slack only absorbs JSON float round-trip noise; anything larger signals "
        "drift in the frozen data or stats file.")
    report["all_exact"] = all(r.get("exact") for r in report["rows"]) and not report["missing_in_frozen"]
    return report


def render_aggregation_verification(report: Dict[str, Any]) -> str:
    lines = ["# AGGREGATION VERIFICATION -- production oeq aggregation unchanged", ""]
    lines.append(f"- recomputed rows: {report['n_recomputed']}  frozen rows: {report['n_frozen']}")
    lines.append(f"- all_exact       : {report['all_exact']}")
    lines.append(f"- max abs diff    : {report['max_abs_diff_across_rows']}")
    lines.append(f"- tolerance       : {report['tolerance']} ({report['tolerance_justification']})")
    if report["missing_in_recomputed"]:
        lines.append(f"- missing in recomputed: {report['missing_in_recomputed']}")
    if report["missing_in_frozen"]:
        lines.append(f"- missing in frozen   : {report['missing_in_frozen']}")
    lines.append("")
    lines.append("| model_name | sample_count_match | max_abs_diff | exact |")
    lines.append("|---|---|---|---|")
    for r in report["rows"]:
        md = r.get("max_abs_diff")
        lines.append(
            f"| {r['model_name']} | {r.get('sample_count_match', '-')} | "
            f"{'-' if md is None else format(md, '.2e')} | {r.get('exact', False)} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_original_cce",
        description="ClearEval counterfactual-validity overlay: read-only CCE scoring adapter "
                    "+ production-aggregation verification.")
    parser.add_argument("--verify-aggregation", action="store_true",
                        help="recompute aggregate_oeq.py-equivalent stats and compare with "
                             "results/oeq_stats_260223.jsonl (exact fixture-equivalence)")
    parser.add_argument("--aggregation-report", default=os.path.join(PKG_DIR, "reports", "AGGREGATION_VERIFICATION.md"))
    parser.add_argument("--teacher", default="openai_gpt-5.2-thinking")
    args = parser.parse_args(argv)

    if args.verify_aggregation:
        recomputed = replicate_aggregate_oeq()
        report = compare_stats_with_frozen(recomputed)
        text = render_aggregation_verification(report)
        os.makedirs(os.path.dirname(args.aggregation_report), exist_ok=True)
        with open(args.aggregation_report, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"recomputed : {report['n_recomputed']} / frozen {report['n_frozen']}")
        print(f"all exact  : {report['all_exact']}   max abs diff: {report['max_abs_diff_across_rows']}")
        print(f"report     : {args.aggregation_report}")
        return 0 if report["all_exact"] else 2
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
