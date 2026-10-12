# ClearEval supplementary experiments: 2026-10-12 research checkpoint

This development checkpoint preserves actual results, implementation snapshots,
negative findings, and the current research questions. It does not replace the
released benchmark scores or certify a complete, validated evaluator.

Start with [当前现状与待解决问题](CURRENT_STATE_zh.md), then read
[the actual intervention-validation report](workspace/reports/cleareval_20261012/intervention_validation_01/REPORT_zh.md).

## What is included

- Exact snapshots of the October 12 reports, per-answer tables, available source
  mappings, saved translation outputs, diagnostic matrices, and failed revisions.
- Local CCE experiment scripts and selected runtime files under
  `workspace/ClearEval-public/`. These are historical implementation snapshots;
  they are deliberately separate from the repository's current production code.
- Current status and experimental plans under `workspace/`.
- A portable, standard-library offline replay of the principal new diagnostics.

Original SR/SP, the MPNet encoder, the 0.7 threshold, and the original CCE/EGES
results remain intact. Constrained matching and operation-bridge outputs are
auxiliary results. No new model requests or expert labels were produced by
preparing this checkpoint. The local request ledger was at 446/446.

## Offline replay

With Python 3.10+ from the repository root:

```sh
python -B experiments/cleareval_supplement_20261012/replay.py
```

The command verifies exported file hashes, reruns numbering normalization and
content-changing controls, and recomputes raw SR/SP and the capacity/phase
diagnostics from the saved similarity matrices. It does not download a model,
call an API, regenerate embeddings, rerun translation, or estimate new stochastic
stability. A successful replay establishes arithmetic/artifact consistency;
the negative scientific findings remain negative.

## Snapshot boundaries

`snapshot_manifest.json` records each exported file's exact source bytes and
workspace-relative origin. Historical manifests inside the snapshots may point
to older local files not included here; those manifests are preserved as records,
not advertised as a complete portable dependency closure. Windows absolute paths
in historical files identify original sources. The portable replay uses paths
relative to this package.

This is not a complete backup of the original machine. API credentials, model
weights, the complete earlier `artifacts/cce_validation/` tree, manuscript source,
and unavailable expert/wet-lab data are not included. Original diagnostic scripts
may require that earlier local environment; use the replay entry above for the
explicitly supported offline checks.

All inspected examples are development-exposed. An available source quotation,
valid JSON, or a higher numeric score does not establish extraction accuracy,
scientific correctness, or fresh-holdout performance.
