"""Development-only, source-preserving numbering view; no semantic rewriting.

Scope: explicit numbered outlines inside a Protocol Steps block. The source and
offset sidecar are retained separately from the proposed translator input.
"""
import hashlib
import re
from collections import Counter

VERSION = "protocol-outline-with-bound-crossrefs-dev1"
PREFIX = re.compile(r"^([ \t]*(?:\*\*)?)(\d+(?:\.\d+)*)([.)]?)([ \t]+)(.+)")
QUANTITY = re.compile(r"^(?:%|(?:[numkµμ]?l|[numkµμ]?g|mm|cm|m|hours?|hrs?|minutes?|mins?|days?|times?|pH|kDa)\b|℃|°|次|小时|分钟)", re.I)
REF_PATTERNS = [
    re.compile(r"\b(?:steps?|sections?|repeat)\s+(\d+(?:\.\d+)*)\b", re.I),
    re.compile(r"\bsame[^\n.;]{0,90}?\bas\s+(\d+(?:\.\d+)*)\b", re.I),
    re.compile(r"(?:重复|步骤|章节)\s*(\d+(?:\.\d+)*)"),
    re.compile(r"(?:与|和)\s*(\d+(?:\.\d+)*)(?=\s*(?:同|共|一起))"),
]


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def apply_edits(text, edits):
    ordered = sorted(edits, key=lambda e: e["start"])
    parts, cursor, outpos, mapped = [], 0, 0, []
    for e in ordered:
        assert e["start"] >= cursor
        assert text[e["start"]:e["end"]] == e["old"]
        copied = text[cursor:e["start"]]
        parts.extend([copied, e["new"]])
        outpos += len(copied)
        mapped.append({**e, "view_start": outpos, "view_end": outpos + len(e["new"])})
        outpos += len(e["new"])
        cursor = e["end"]
    parts.append(text[cursor:])
    view = "".join(parts)
    inverse = [{"start": e["view_start"], "end": e["view_end"], "old": e["new"], "new": e["old"]} for e in mapped]
    recovered = view
    for e in reversed(inverse):
        recovered = recovered[:e["start"]] + e["new"] + recovered[e["end"]:]
    assert recovered == text
    return view, mapped


def canonicalize(text):
    marker = re.search(r"Protocol Steps", text, re.I)
    begin = text.find("\n", marker.end()) + 1 if marker else 0
    # Without an explicit block, preserve the document and report the scope gap.
    if not marker or begin == 0:
        return {"version": VERSION, "view": text, "view_sha256": digest(text), "nodes": [], "edits": [], "references": [], "issues": ["no_explicit_protocol_block"], "roundtrip_exact": True}
    lines, offset = [], begin
    for raw in text[begin:].splitlines(keepends=True):
        m = PREFIX.match(raw)
        if m:
            lines.append({"label": m[2], "punctuation": m[3], "start": offset, "end": offset + len(raw),
                          "label_start": offset + m.start(2), "label_end": offset + m.end(2),
                          "body_start": offset + m.start(5), "body": raw[m.start(5):], "source_quote": raw})
        offset += len(raw)
    counts = Counter(r["label"] for r in lines)
    labels = set(counts)
    nodes, issues = [], []
    for row in lines:
        label = row["label"]
        has_child = any(x.startswith(label + ".") for x in labels)
        has_parent = "." in label and label.rsplit(".", 1)[0] in labels
        quantity = bool(QUANTITY.match(row["body"].lstrip("* ")))
        if counts[label] != 1:
            issues.append("ambiguous_repeated_label:" + label)
        elif not quantity and (has_child or has_parent or row["punctuation"]):
            nodes.append({**row, "node_id": "N%04d" % (len(nodes) + 1)})
    node_by_label = {n["label"]: n for n in nodes}
    for n in nodes:
        parent = node_by_label.get(n["label"].rsplit(".", 1)[0]) if "." in n["label"] else None
        n["parent_id"] = parent["node_id"] if parent else None
    edits = [{"start": n["label_start"], "end": n["label_end"], "old": n["label"], "new": n["node_id"], "kind": "display_label", "node_id": n["node_id"]} for n in nodes]
    refs, seen = [], set()
    for n in nodes:
        for pattern in REF_PATTERNS:
            for hit in pattern.finditer(n["body"]):
                label = hit[1]
                tail = n["body"][hit.end(1):]
                if re.match(r"\s*(?:%|times?\b|次|hours?\b|小时)", tail, re.I):
                    continue
                start = n["body_start"] + hit.start(1)
                end = n["body_start"] + hit.end(1)
                if (start, end) in seen:
                    continue
                seen.add((start, end))
                target = node_by_label.get(label)
                ref = {"start": start, "end": end, "literal": label, "from_node": n["node_id"], "target_node": target["node_id"] if target else None, "context": hit[0]}
                refs.append(ref)
                if target:
                    edits.append({"start": start, "end": end, "old": label, "new": target["node_id"], "kind": "cross_reference", "node_id": target["node_id"]})
                else:
                    issues.append("unresolved_cross_reference:" + label)
    view, mapped = apply_edits(text, edits)
    return {"version": VERSION, "view": view, "view_sha256": digest(view), "nodes": nodes, "references": refs,
            "edits": mapped, "issues": issues, "roundtrip_exact": True,
            "scope": "explicit protocol outline; no heading exclusion or operation decomposition", "source_sha256": digest(text)}


def renumber(text, delta=100, update_references=True):
    parsed = canonicalize(text)
    mapping = {n["label"]: str(int(n["label"].split(".")[0]) + delta) + ("." + n["label"].split(".", 1)[1] if "." in n["label"] else "") for n in parsed["nodes"]}
    edits = []
    for e in parsed["edits"]:
        if e["kind"] == "display_label" or update_references:
            edits.append({"start": e["start"], "end": e["end"], "old": e["old"], "new": mapping[e["old"]]})
    return apply_edits(text, edits)[0]
