"""Loopback-only, frozen, resumable Ollama requests with explicit attempt IDs."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request

from .contract import adjudicate, canonical, digest, file_hash, parse_json, read, save, validate_extraction
from .execution_identity import assert_public, execution_identity, public_context


def now():
    return datetime.now(timezone.utc).isoformat()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def local_origin(url):
    p = urllib.parse.urlsplit(url)
    if (p.scheme != "http" or p.hostname not in {"127.0.0.1", "::1", "localhost"}
            or p.username or p.password or p.query or p.fragment or p.path not in {"", "/"}):
        raise ValueError("Only explicit loopback Ollama origins allowed")
    # Restrict to literal loopback to avoid DNS drift or proxy forwarding.
    if p.hostname == "localhost":
        raise ValueError("Use a literal loopback address")
    return url.rstrip("/")


def opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)


def metadata(origin):
    origin = local_origin(origin)
    info = {}
    for route in ("version", "tags", "ps"):
        with opener().open(origin + "/api/" + route, timeout=20) as response:
            info[route] = json.load(response)
    return info


class ModelBindingError(ValueError):
    pass


def verify_model_binding(manifest):
    """Read-only pre/post identity; this does not certify model determinism."""
    info = metadata(manifest["origin"])
    matches = [m for m in info["tags"].get("models", [])
               if m.get("name") == manifest["model"] and m.get("digest") == manifest["model_digest"]]
    if len(matches) != 1:
        raise ModelBindingError("Frozen model revision is not uniquely available")
    details = matches[0].get("details", {})
    family = details.get("family", "UNDECLARED")
    if manifest.get("model_family") and manifest["model_family"] != family:
        raise ModelBindingError("Runtime judge family differs from declared family")
    return {"model":manifest["model"], "digest":manifest["model_digest"],
            "family":family, "server_version":info.get("version", {}).get("version")}



def verify_manifest(study):
    study = Path(study)
    m = read(study/"manifest.json")
    if digest({k:v for k,v in m.items() if k != "manifest_sha256"}) != m["manifest_sha256"]:
        raise ValueError("Manifest content changed")
    for rel, expected in m["files"].items():
        if file_hash(study/rel) != expected:
            raise ValueError("Frozen input changed: " + rel)
        if rel.startswith("code/") and file_hash(Path(__file__).parent/Path(rel).name) != expected:
            raise ValueError("Executing module differs from frozen code: " + rel)
    return m


def build_payload(study, manifest, job):
    material = read(Path(study)/"materials.json")[job["material_id"]]
    if material.get("generation_job") and job["phase"] != "generate":
        from .analysis import checked_attempt
        generation = [j for j in read(Path(study)/"jobs.json") if j["id"] == material["generation_job"]]
        if len(generation) != 1 or generation[0]["phase"] != "generate":
            raise ValueError("Generation dependency is not a uniquely frozen generation job")
        checked_attempt(Path(study), manifest, generation[0])
        folder = Path(study)/"attempts"/material["generation_job"]/"a01"
        result = read(folder/"result.json")
        if result["status"] != "COMPLETE":
            raise ValueError("Generation dependency not complete")
        protocol = (folder/"content.txt").read_text(encoding="utf-8")
        if digest(protocol) != result["content_sha256"]:
            raise ValueError("Generated protocol hash mismatch")
    else:
        protocol = material.get("protocol")
    if job["phase"] == "generate":
        assert_public({"question": material["question"], "resource_list": material["resource_list"]})
        messages = [{"role":"user", "content": "请按任务输出可复核的实验方案，逐步写清必要试剂、条件和时间；未知处明确待确认，不编造。\n任务：\n" + material["question"] + "\n候选资源（列出不保证适用）：\n" + json.dumps(material["resource_list"], ensure_ascii=False)}]
    elif job["phase"] == "extract":
        messages = [{"role":"system", "content": (Path(study)/"extract_prompt.txt").read_text(encoding="utf-8")},
                    {"role":"user", "content": json.dumps(public_context(material, protocol, "extract"), ensure_ascii=False)}]
    else:
        messages = [{"role":"system", "content": (Path(study)/"judge_prompt.txt").read_text(encoding="utf-8")},
                    {"role":"user", "content": json.dumps(public_context(material, protocol), ensure_ascii=False)}]
    options = dict(manifest["options"])
    options.update(manifest["phase_options"][job["phase"]])
    payload = {"model": manifest["model"], "messages": messages, "stream":True,
               "think":False, "keep_alive":"30m", "options":options}
    if job["phase"] != "generate":
        payload["format"] = "json"
    return payload, material, protocol


def run_job(study, manifest, job, attempt="a01", *, transport=None):
    """No silent retry. Repeats are distinct planned jobs with identical payloads."""
    study = Path(study)
    if attempt != "a01":
        raise ValueError("This version permits one explicit attempt per planned job")
    folder = study/"attempts"/job["id"]/attempt
    if (folder/"started.json").exists():
        raise ValueError("Job already attempted; never resend implicitly")
    payload, material, protocol = build_payload(study, manifest, job)
    endpoint = local_origin(manifest["origin"]) + "/api/chat"
    identity = execution_identity(payload, material, protocol, manifest, job)
    invocation_id = str(uuid.uuid4())
    origin = "TEST_TRANSPORT" if transport else "LIVE"
    save(folder/"request.json", {"endpoint":endpoint, "payload":payload, "payload_sha256":digest(payload),
                                 "execution_identity":identity})
    save(folder/"started.json", {"created_at":now(), "job":job, "manifest_sha256":manifest["manifest_sha256"],
                                 "invocation_id":invocation_id, "execution_origin":origin})
    result = {"job_id":job["id"], "attempt":attempt, "phase":job["phase"], "material_id":job["material_id"],
              "root_task_id":material["root_task_id"], "status":"FAILED", "payload_sha256":digest(payload),
              "started_at":now(), "model":manifest["model"], "model_digest":manifest["model_digest"],
              "execution_identity_sha256":digest(identity), "invocation_id":invocation_id,
              "execution_origin":origin, "response_cache_hit":False,
              "visible_information_sha256":identity["visible_information_sha256"],
              "technical_status":"PENDING", "request_sent":False}
    started, parts, terminal = time.monotonic(), [], None
    print(json.dumps({"job":job["id"], "status":"STARTED"}), flush=True)
    try:
        if transport is None:
            result["model_binding_before"] = verify_model_binding(manifest)
        request = urllib.request.Request(endpoint, data=canonical(payload), headers={"Content-Type":"application/json"})
        result["request_sent"] = True
        response = transport(request) if transport else opener().open(request, timeout=manifest["read_timeout_seconds"])
        with response, (folder/"chunks.jsonl").open("x", encoding="utf-8") as output:
            for line in response:
                chunk = parse_json(line.decode("utf-8"))
                output.write(json.dumps(chunk, ensure_ascii=False)+"\n")
                output.flush()
                if chunk.get("error"):
                    raise RuntimeError(str(chunk["error"]))
                content = chunk.get("message", {}).get("content", "")
                if content:
                    if not parts:
                        result["first_content_seconds"] = round(time.monotonic()-started,3)
                        print(json.dumps({"job":job["id"], "first_content_seconds":result["first_content_seconds"]}),flush=True)
                    parts.append(content)
                if time.monotonic()-started > manifest["wall_limit_seconds"]:
                    raise TimeoutError("Request wall limit exceeded")
                if chunk.get("done"):
                    terminal = chunk
        if terminal is None:
            raise ValueError("Stream ended without terminal response")
        save(folder/"terminal_response.json", terminal)
        result["runtime"] = {k:terminal.get(k) for k in ("model", "done_reason", "prompt_eval_count", "eval_count", "total_duration", "load_duration", "prompt_eval_duration", "eval_duration")}
        if terminal.get("model") != manifest["model"]:
            raise ValueError("Returned model differs from frozen model")
        if terminal.get("done_reason") != "stop":
            result["status"] = "TRUNCATED"
            raise ValueError("Generation hit a limit or stopped abnormally")
        text = "".join(parts)
        if job["phase"] == "generate":
            if len(text.strip()) < 30:
                raise ValueError("Empty or insufficient generated text")
        else:
            value = parse_json(text)
            save(folder/"parsed.json", value)
            if job["phase"] == "extract":
                validated = validate_extraction(value, protocol)
            else:
                validated = adjudicate(value, material["requirements"], protocol, material["cards"], material.get("formula"))
            save(folder/"validated.json", validated)
        if transport is None:
            result["model_binding_after"] = verify_model_binding(manifest)
        result["status"] = "COMPLETE"
        result["technical_status"] = "VALID"
    except (Exception, KeyboardInterrupt) as exc:
        if isinstance(exc, (TimeoutError, socket.timeout)):
            result["status"] = "TIMEOUT"
        elif isinstance(exc, KeyboardInterrupt):
            result["status"] = "INTERRUPTED"
        if isinstance(exc, ModelBindingError):
            kind = "MODEL_BINDING_FAILURE"
        elif isinstance(exc, (TimeoutError, socket.timeout, urllib.error.URLError, ConnectionError)):
            kind = "TRANSPORT_FAILURE"
        elif isinstance(exc, json.JSONDecodeError):
            kind = "PARSE_FAILURE"
        elif result["status"] == "TRUNCATED":
            kind = "TRUNCATED_RESPONSE"
        elif isinstance(exc, KeyboardInterrupt):
            kind = "INTERRUPTED"
        elif isinstance(exc, ValueError):
            kind = "SCHEMA_OR_STREAM_FAILURE"
        else:
            kind = "RUNTIME_FAILURE"
        result["technical_status"] = kind
        result["failure"] = {"type":type(exc).__name__, "kind":kind, "message":str(exc)[:300]}
    finally:
        text = "".join(parts)
        (folder/"content.txt").write_text(text,encoding="utf-8")
        result["content_sha256"] = digest(text)
        result["elapsed_seconds"] = round(time.monotonic()-started,3)
        result["completed_at"] = now()
        save(folder/"result.json", result)
    print(json.dumps({k:result.get(k) for k in ("job_id", "status", "elapsed_seconds", "failure")},ensure_ascii=False),flush=True)
    return result


def run(study, max_new, phases=None):
    study = Path(study)
    m = verify_manifest(study)
    info = metadata(m["origin"])
    tags = info["tags"].get("models", [])
    if not any(x.get("name") == m["model"] and x.get("digest") == m["model_digest"] for x in tags):
        raise ValueError("Frozen model digest is unavailable locally")
    snapshot = study/"runtime"/(str(time.time_ns())+".json")
    save(snapshot, info)
    jobs = read(study/"jobs.json")
    executed = 0
    for job in jobs:
        if executed >= max_new:
            break
        if phases and job["phase"] not in phases:
            continue
        if (study/"attempts"/job["id"]/"a01"/"started.json").exists():
            continue
        if sum(1 for _ in (study/"attempts").glob("*/a01/started.json")) >= m["max_calls"]:
            raise ValueError("Frozen request budget exhausted")
        try:
            build_payload(study,m,job)
        except (FileNotFoundError, ValueError):
            continue  # Unmet dependencies remain visibly unattempted in report.
        result = run_job(study,m,job)
        executed += 1
        # Stop only on service/transport failure; retain parse failures and proceed
        # to independent jobs under the predeclared fixed plan, never retry for score.
        if result["status"] in {"TIMEOUT", "INTERRUPTED"} or result.get("failure",{}).get("type") in {"URLError", "ConnectionError"}:
            return {"executed":executed, "paused":"TRANSPORT_FAILURE"}
    return {"executed":executed, "paused":None}
