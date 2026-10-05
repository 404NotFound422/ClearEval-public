"""Explicit scientific release gates, distinct from engineering test success."""
from pathlib import Path
from .contract import read,save

def formal_readiness(workspace,output):
    workspace,output=Path(workspace),Path(output)
    base=workspace/"review_artifacts/engineering_2026-09-29"
    # This release has no approved domain decisions or eligible holdout.
    # Importing reviews does not silently approve a new scientific contract.
    imports=list((base/"expert_ratings").glob("*/import_status.json"))
    imported=sum(read(p)["accepted"] for p in imports)
    gates=[
      {"id":"DOMAIN_CONTRACT","passed":False,"reason":"Draft task requirements/evidence require domain approval and a new frozen release"},
      {"id":"INDEPENDENT_REFERENCE","passed":False,"reason":"Two independent first-pass reviewers and disagreement handling required","imported_rows":imported},
      {"id":"SOURCE_GROUPED_HOLDOUT","passed":False,"reason":"No reviewed, independently reserved source groups in this release"},
      {"id":"FULL_BASELINE_IMPLEMENTATION","passed":False,"reason":"Legacy replay and guard ablation exist; full B0-B4 same-input comparison remains pending"},
      {"id":"FINAL_MODEL_AND_SAMPLE_MANIFEST","passed":False,"reason":"Current manifest is a one-model development run, not the formal comparison"}]
    value={"formal_ready":False,"gates":gates,"status":"PENDING_INDEPENDENT_REFERENCE_AND_FORMAL_RELEASE",
           "note":"Engineering tests, source presence, and imported files alone cannot authorize scientific validity claims."}
    save(output/"formal_readiness.json",value,immutable=False)
    return value
