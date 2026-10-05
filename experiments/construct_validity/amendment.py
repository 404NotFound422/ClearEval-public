"""Explicit transport-only amendment; original failures remain unchanged."""
from pathlib import Path
from .contract import digest,file_hash,read,save
from .local_runner import verify_manifest

def longer_initial_wait(parent,output):
    parent,output=Path(parent).resolve(),Path(output).resolve()
    if (output/"manifest.json").exists(): return verify_manifest(output)
    m=verify_manifest(parent)
    results=[read(p) for p in sorted((parent/"attempts").glob("*/a01/result.json"))]
    if not results or any(r["status"]!="TIMEOUT" for r in results):
        raise ValueError("Amendment restricted to an all-timeout initial batch")
    for rel in m["files"]:
        target=output/rel
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists(): raise ValueError("Partial amendment exists; inspect first")
        target.write_bytes((parent/rel).read_bytes())
    amendment={"parent_manifest_sha256":m["manifest_sha256"],"parent_path":str(parent),
        "reason":"Both 180-second initial-content waits expired. CPU model now appears loaded. One bounded transport-only retry uses the previously successful 480-second read timeout.",
        "changes":{"read_timeout_seconds":[m["read_timeout_seconds"],480]},
        "scientific_inputs_or_sampling_changed":False,"parent_results":results,
        "stop_if_first_retry_times_out":True,"further_transport_retries":0}
    save(output/"amendment.json",amendment)
    m["read_timeout_seconds"]=480
    m["parent_manifest_sha256"]=amendment["parent_manifest_sha256"]
    m["files"]["amendment.json"]=file_hash(output/"amendment.json")
    m.pop("manifest_sha256")
    m["manifest_sha256"]=digest(m)
    save(output/"manifest.json",m)
    return m
