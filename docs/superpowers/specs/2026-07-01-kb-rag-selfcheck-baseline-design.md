# Inference-Time Baseline: KB-RAG + Self-Check on the 253 Application OEQs

**Date:** 2026-07-01
**Status:** Approved (design decisions locked); implementing pilot-first.
**Owner:** ClearEval / article/BIBM

## 1. Objective

Add a small inference-time baseline to the ClearEval paper that measures how far two
cheap, deployment-realistic interventions move the **Application Index** `I_A` on the
full 253 open-ended questions (OEQ = the Application track; MCQ/Knowledge track is not
re-run):

- **1-shot** — existing canonical results, reused as-is (no regeneration).
- **1-shot + KB-RAG** — prepend a per-scenario, non-leaky knowledge-base context.
- **1-shot + KB-RAG + self-check** — after the grounded answer, run one fixed-checklist
  self-check + single revision (cheaper substitute for self-consistency `k=5`).

Models: `openai_gpt-5.2-fast`, `openai_qwen3-max`, `openai_qwen3-14b`.

The experiment fills the paper's **Section 4.5 (Inference-Time Robustness Protocol)**,
which currently defers results.

## 2. Scoring background (what we are trying to move)

From `OEQ_run_grading_new.py` + `results/calculate_main_table_score.py` + the paper:

- `I_A = min(Completeness, Correctness, Effectiveness)` (bottleneck).
- `Effectiveness = max(0, mean(S_method_hat, S_label_hat, S_trans_hat, S_time_hat))` — rule-based, KB lookups.
- `S_label = min(S_target, S_marker, S_method-marker)` (max 6). Mean ~= 0.34, ~51% score 0.
- `S_trans = 3*exp(-(RI_tissue - RI_ref)^2 / 2*sigma_RI^2)` (max 3). Gate: unsupported (method, tier) -> 0.
- `S_time = 3*exp(-dt^2 / 2*tau^2)` (max 3), `tau = 0.2*median`. Same applicability gate.
- `S_method` signed (+-2.5) = `2.5 * sum(d_a c_a) / sum(d_a)`, `d_a = w_a t_a` (demand vector x method capability).

**Key fact:** For 12/13 models `I_A = Effectiveness`, and `S_label` (marker-target mismatch)
is the dominant zeroed sub-metric. KB-RAG's lever is therefore correct: grounding `S_label`
(and avoiding the `S_trans/S_time` applicability gate) lifts Effectiveness -> `I_A`.

## 3. Non-leakage boundary (releasable policy)

Cards B/C/D/E derive from the *same* KB tables the evaluator scores against, so the boundary
must be explicit. This table is part of the released artifact.

| KB content | Source file | In main-text KB-RAG? | Form exposed |
|---|---|---|---|
| Method property / family / sample fit | `KnowledgeBase/method_ri_ref.json`, `dataset/Q+AR/src/model_space_signed.json` | Yes | Qualitative (family, tiers, strengths/limits) |
| Target -> marker candidates | `KnowledgeBase/tissue.json` | Yes (**Balanced**: category-level candidate set, not the single gold string) | Marker names + labeling strategy + false-friends |
| Marker <-> fluorophore compatibility | `KnowledgeBase/tissue.json` (0/1 cols) | Yes | Status `compatible/caution/avoid` (not raw 0/1) |
| Method <-> fluorophore compatibility | `KnowledgeBase/method_fluro_compati.json` (0-1) | Yes | Status `compatible/caution/avoid` (score binned, raw value hidden) |
| Method supports a sample tier | `KnowledgeBase/time_kb.json` (`supported`) | Yes | Qualitative "supported / not established for this tier" |
| Qualitative timing order | derived from `time_kb.json` | Yes | hours / overnight / days / weeks bucket only |
| Exact `[t_min, t_max]`, median time | `time_kb.json` | **No** | withheld |
| `tau`, `sigma_RI`, `RI_ref`, tissue RI values | `method_time_tau.json`, `method_sigma_ri.json`, `method_ri_ref.json` RI, `tissue_ri.json` | **No** | withheld |
| Marker specificity tiers (0/3/6) | `workflow/s_label_audit/marker_specificity_tiers.json` | **No** | withheld |
| Gold/reference protocol, "best method" label, prior model outputs, expert scores | various | **No** | withheld |

Framing in the paper: KB-RAG is an **upper bound on grounding benefit**; numeric scorer
windows/tolerances are never in the context.

## 4. RAG context: five compact cards per scenario

One `dataset/Q+AR/rag_context/rag_context_{question_id}.json` per OEQ (253 files),
**identical across models** (retrieval keyed on OEQ metadata, never on a model parse).

- **A. Scenario slot card** - from `question_final.json`
  (`tissue_inferred`, `tissue_tier_code/label`, per-target `structure_or_cell_subtype` +
  `major_category/subcategory`) plus a **structured constraint block from
  `demand_vectors_all.json`** (6 axes -> human-readable needs). Fallback for the ~50-60
  OEQ lacking a demand vector: derive constraints qualitatively from tissue category + tier.
- **B. Target-marker card (Balanced)** - for each target, retrieve `tissue.json` rows by
  `major_category`/`subcategory` -> candidate markers (gold marker included in the set, not
  singled out), valid labeling strategies, and generic false-friends. No specificity tiers.
- **C. Candidate method cards** - 18-method **mini-index** (one line each: family, tier fit,
  strengths/limits) + **top-5 full cards**. Retrieval is **qualitative rule-based**
  (tier-support from `time_kb.json`, family fit for the preservation/penetration needs),
  **explicitly NOT the `S_method` demand.capability dot product**. Full cards give family,
  supported tiers, strengths/limitations, labeling notes, qualitative RI/time descriptors,
  safety. No numeric windows/tolerances.
- **D. Method x marker/fluorophore compatibility cross-card** - top-5 methods x
  Card-B candidate markers/fluorophores, from `tissue.json` cols + `method_fluro_compati.json`,
  emitted as `status in {compatible, caution, avoid}` + short reason. Raw scores hidden.
- **E. RI / timing / tier-feasibility card** - per candidate method: "supported / not
  established for tier X" + qualitative timing bucket. Withhold `[t_min,t_max]`, `sigma_RI`, `tau`,
  gold time.

## 5. Retrieval procedure

1. Read OEQ metadata -> scenario slots (Card A). No model parsing.
2. Target-first: look up target-marker candidates by category/subcategory (Card B).
3. Method candidates: qualitative rule filter over method properties -> top-5 (Card C),
   keep 18-method mini-index as escape hatch.
4. Cross-compat: top-5 methods x Card-B markers/fluorophores -> statuses (Card D).
5. Tier feasibility + qualitative timing/RI (Card E).
6. Compose compact JSON -> `rag_context_{qid}.json` (released).

## 6. Self-check (one grounded revision)

After the KB-RAG answer, a single model call: "Check your protocol against this fixed
checklist, then output a corrected protocol (or repeat unchanged)." Checklist targets the
known failure modes without numbers: (1) does each fluorescent marker match the required
labeling target; (2) marker<->fluorophore compatibility; (3) method<->fluorophore compatibility;
(4) is the chosen method established for this sample tier; (5) is the timing order plausible
for the tier; (6) RI family match. The self-check call re-sees the same KB-RAG context.
Exactly one revise pass. Same checklist for all models.

## 7. Implementation

- **New** `build_rag_context.py` -> writes `dataset/Q+AR/rag_context/rag_context_{qid}.json`
  for all 253 OEQ. Pure local, deterministic, no API calls, releasable. Includes a
  `--sample` mode to print a few cards for inspection.
- **Patch** `OEQ_run_grading_new.py`:
  - `generate_model_prompt(...)` gains a `rag_context` arg -> prepend a "Retrieved
    Knowledge-Base Context" block after Restrictions (template placeholder in
    `prompts/gen_protocol_template.py`).
  - Generation path gains a `self_check` step (one extra grounded `_acall` + revise).
  - New `--shot-types` tokens: `1-shot+KB-RAG`, `1-shot+KB-RAG+self-check`
    (filename-safe token mapping if needed). RAG dir passed via a new `--rag-dir` arg.
  - Existing 1-shot untouched; grader stays `openai_gpt-5.2-thinking` (canonical teacher).
- Outputs follow existing convention:
  `from_{model}_{setting}.json`, `evaluation_results_{model}_{setting}.json`.

## 8. Run plan (pilot-first)

1. Build + eyeball RAG context (no paid calls).
2. **Pilot:** `openai_gpt-5.2-fast` x {`1-shot+KB-RAG`, `1-shot+KB-RAG+self-check`}
   -> grade (gpt-5.2-thinking) -> aggregate -> report `{Com, Cor, Eff, I_A}` + `S_label`
   uplift vs its 1-shot baseline. **Pause for review.**
3. **Scale:** on approval, run `qwen3-max` + `qwen3-14b`, same two settings.

## 9. Reporting & paper

- 3-model x 3-setting table: `Com / Cor / Eff / I_A`, plus Effectiveness sub-scores
  `S_method / S_label / S_trans / S_time` (spotlight `S_label`).
- Fill **Section 4.5** in `article/BIBM/main.tex`: replace the deferred-results text with
  the table + discussion, in the paper's notation (`S_label`, `sigma_RI`, `tau`, `I_A = min(...)`).
  Update the 4.5 description: self-**check** (one grounded revise) substitutes the previously
  promised self-**consistency** (`k=5`), motivated by cost.

## 10. Out of scope

Literature-RAG; MCQ/Knowledge track; changing the evaluator or its constants; regenerating
1-shot; few-shot and self-consistency baselines (self-check replaces the latter).
