"""Freeze published ERR/source materials with model inputs separated from labels."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from evaluation_contract import json_hash

ERR_SHA = "371fad1216ca589a97088c5a7ceb7e2c5c40cd0c88e2224a149ac5a9eaae939e"
METRICS_SHA = "d1ea28e4717cbd9513ccdd7a8a455ce2f78eef9dd1d8d2fa4d7ac97730bf12da"
PROMPT_SHA = "66ebcf18f9222f0c2b8447401242c3a334ad72ab962e932a562d808827214af6"
CORPUS_SHA = "5ed3b7f1120af7442b06e50a14c4dc654dfe096fbb7db93e834433f2b43806e9"
GITHUB_REVISION = "cf00fecd62583b98350cc48e26a29c92d3f21e5d"
HF_REVISION = "dec67450c8040250ea7751c7a3e77b3ac1e2e853"
DOMAIN_TERMS = ("clearing", "immunostain", "histolog", "fluorescen", "brain", "confocal")
# This materials builder selects ordinary analysis protocols and does not make
# requests to optimize pathogens, virulence, toxins, or delivery systems.
OUT_OF_SCOPE = re.compile(r"virus|viral|pathogen|lentivir|adenovir|HIV|SARS|influenza|anthrax|botulin|toxin|virulen", re.I)
FORBIDDEN_MODEL_FIELDS = {"is_correct", "corrected_text", "error_description", "gold",
                          "labels", "expected", "label_origin"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bound_read(path, expected):
    data = Path(path).read_bytes()
    if sha(data) != expected:
        raise ValueError("Published source snapshot hash mismatch: " + Path(path).name)
    return data


def load_official_functions(path, expected_hash, names):
    data = bound_read(path, expected_hash)
    tree = ast.parse(data.decode("utf-8"))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in nodes} != set(names):
        raise ValueError("Official function missing")
    namespace = {"re": re}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return {name: namespace[name] for name in names}


def official_err_parse(text, upstream):
    functions = load_official_functions(Path(upstream) / "Metrics__ERR.py", METRICS_SHA,
                                        ["extract_binary_answer"])
    return functions["extract_binary_answer"](text)


def official_err_metrics(predictions, gold, upstream):
    if len(predictions) != len(gold) or any(type(value) is not bool for value in predictions + gold):
        raise ValueError("ERR metrics require aligned Boolean predictions and labels")
    functions = load_official_functions(Path(upstream) / "Metrics__ERR.py", METRICS_SHA,
                                        ["compute_classification_metrics"])
    return functions["compute_classification_metrics"](predictions, gold)


def strict_err_parse(text):
    match = re.fullmatch(r"\s*(?:\[ANSWER_START\]\s*)?(True|False)(?:\s*\[ANSWER_END\])?\s*", text)
    if match is None:
        raise ValueError("Ambiguous or invalid ERR answer")
    if ("[ANSWER_START]" in text) != ("[ANSWER_END]" in text):
        raise ValueError("Incomplete ERR answer tags")
    return match.group(1) == "True"


def whitespace_only(text):
    return re.sub(r"\s+", " ", text).strip()


def flatten(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(flatten(item) for item in value)
    if isinstance(value, dict):
        return "\n".join(flatten(item) for item in value.values())
    return ""


def source_join(err_rows, protocols):
    """Return unique original-source joins. Never substitute row ID for source ID."""
    bodies = [whitespace_only(flatten(row["protocol"])) for row in protocols]
    joined, unavailable = {}, []
    for row in err_rows:
        needle = whitespace_only(row["corrected_text"])
        matches = [index for index, body in enumerate(bodies) if needle and needle in body]
        if len(matches) == 1:
            joined[row["id"]] = protocols[matches[0]]
        else:
            unavailable.append({"id": row["id"], "source_matches": len(matches),
                                "source_grouping": "UNAVAILABLE_NO_UNIQUE_EXACT_JOIN"})
    return joined, unavailable


def grouped_split(groups, salt="cleareval-original-source-holdout-v1"):
    """Split source groups before inspecting labels; no row-level leakage."""
    ordered = sorted(set(groups), key=lambda group: sha((salt + "\n" + group).encode("utf-8")))
    if len(ordered) < 2:
        return {group: "UNASSIGNED_INSUFFICIENT_SOURCE_GROUPS" for group in ordered}
    n_holdout = max(1, len(ordered) // 3)
    return {group: "holdout" if index < n_holdout else "development"
            for index, group in enumerate(ordered)}


def audit_input_separation(cases, labels):
    label_map = {row["label_key"]: row for row in labels}
    if len(label_map) != len(labels):
        raise ValueError("Duplicate hidden label keys")
    seen = set()
    def inspect(value):
        if isinstance(value, dict):
            if FORBIDDEN_MODEL_FIELDS & set(value):
                raise ValueError("Gold field present in model input")
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)
    source_splits = {}
    for case in cases:
        if case["id"] in seen or case["label_key"] not in label_map:
            raise ValueError("Duplicate case or missing independent label")
        seen.add(case["id"])
        inspect(case["input"])
        if case["input_sha256"] != json_hash(case["input"]):
            raise ValueError("Model input canonical hash mismatch")
        group = case["source_group"]
        if group is not None:
            if group in source_splits and source_splits[group] != case["split"]:
                raise ValueError("Original source leaks across development and holdout")
            source_splits[group] = case["split"]
    return {"input_separation": "VALID", "cases": len(cases), "source_groups": len(source_splits),
            "scientific_accuracy": None, "expert_consistency": None}


def err_materials(upstream):
    upstream = Path(upstream)
    rows = json.loads(bound_read(upstream / "Data__ERR_test.json", ERR_SHA))
    protocols = json.loads(bound_read(upstream / "Protocol-exchange.json", CORPUS_SHA))
    functions = load_official_functions(upstream / "Scripts__prompt_format.py", PROMPT_SHA,
                                        ["generate_user_prompt"])
    joins, unavailable = source_join(rows, protocols)
    eligible = []
    for row in rows:
        original = joins.get(row["id"])
        if original is not None and not OUT_OF_SCOPE.search(flatten(original["protocol"])):
            eligible.append((row, original))
    groups = [original["url"].strip() for _, original in eligible]
    splits = grouped_split(groups)
    cases, labels, fragments = [], [], []
    for row in rows:
        if any(term in json.dumps(row, ensure_ascii=False).casefold() for term in DOMAIN_TERMS):
            if OUT_OF_SCOPE.search(json.dumps(row, ensure_ascii=False)):
                continue
            prompt = functions["generate_user_prompt"](row, "ERR")
            # is_correct selects the presented target, exactly as the official
            # prompt does. Its value, correction and error rationale stay hidden.
            payload = {"protocol": row["corrected_text"] if row["is_correct"] else row["corrupted_text"],
                       "requirements": ["Judge the target step in its provided context."],
                       "context": row["context"], "source_cards": [], "official_prompt": prompt}
            key = "bioprobench-fragment:" + row["id"]
            original = joins.get(row["id"])
            group = original["url"].strip() if original else None
            fragments.append({"id": key, "task_id": "BioProBench_ERR_OFFICIAL_INFORMATION",
                              "source_group": group,
                              "split": splits.get(group, "UNASSIGNED_NO_SOURCE_ID"),
                              "input": payload, "input_sha256": json_hash(payload), "label_key": key})
            labels.append({"label_key": key, "label_origin": "PUBLISHED_BIOPROBENCH_OFFICIAL_TEST",
                           "labels": {"is_correct": row["is_correct"]}, "upstream_id": row["id"],
                           "error_type": row["type"],
                           "provenance": {"repository_revision": GITHUB_REVISION, "raw_sha256": ERR_SHA},
                           "independent_of_cleareval": True, "wet_lab_success": None})
    for row, original in eligible:
        group = original["url"].strip()
        protocol = flatten(original["protocol"])
        prompt = functions["generate_user_prompt"](row, "ERR")
        payload = {"protocol": row["corrected_text"] if row["is_correct"] else row["corrupted_text"],
                   "requirements": ["Judge the target step using the same provided full original protocol."],
                   "context": row["context"],
                   "source_cards": [{"id": original["id"], "url": group, "title": original["title"],
                                     "protocol": protocol, "protocol_sha256": sha(protocol.encode("utf-8"))}],
                   "official_prompt": prompt}
        key = "bioprobench-full-context:" + row["id"]
        cases.append({"id": key, "task_id": "BioProBench_ERR_EXTENDED_FULL_SOURCE_CONTEXT",
                      "source_group": group, "split": splits[group], "input": payload,
                      "input_sha256": json_hash(payload), "label_key": key})
        labels.append({"label_key": key, "label_origin": "PUBLISHED_BIOPROBENCH_OFFICIAL_TEST",
                       "labels": {"is_correct": row["is_correct"]}, "upstream_id": row["id"],
                       "error_type": row["type"],
                       "provenance": {"repository_revision": GITHUB_REVISION, "raw_sha256": ERR_SHA,
                                      "corpus_revision": HF_REVISION, "corpus_sha256": CORPUS_SHA,
                                      "source_id": original["id"], "source_url": group,
                                      "join": "UNIQUE_CORRECTED_STEP_SUBSTRING_WHITESPACE_ONLY"},
                       "independent_of_cleareval": True, "wet_lab_success": None})
    audit_input_separation(cases + fragments, labels)
    return cases, fragments, labels, {
        "official_ERR_total": len(rows), "official_label_counts": dict(Counter(str(row["is_correct"]) for row in rows)),
        "full_source_unique_joins": len(joins), "full_source_safe_selected": len(cases),
        "domain_fragment_selected": len(fragments),
        "domain_full_source_selected": sum(any(term in json.dumps(case["input"], ensure_ascii=False).casefold()
                                              for term in DOMAIN_TERMS) for case in cases),
        "unavailable_original_source_mapping": len(unavailable),
        "split_rule": "GROUPED_BY_ORIGINAL_SOURCE_URL_BEFORE_LABEL_INSPECTION",
        "original_paper_metric_comparison": "FULL_CONTEXT_IS_INFORMATION_EXTENDED_NOT_ORIGINAL_BENCHMARK",
        "clearing_domain_holdout_validity": "NOT_ESTABLISHED_TOO_FEW_RELEVANT_BOUND_SOURCES",
        "source_split": splits,
    }


def primary_materials(workspace):
    root = Path(workspace)
    registry = json.loads((root / "KnowledgeBase/source_registry.json").read_text(encoding="utf-8"))
    sources = [source for source in registry["sources"] if source.get("snapshot") and source.get("passages")]
    def group(source):
        # The correction and the protocol belong to one version family.
        return "SEEDB2_PROTOCOL_VERSION_FAMILY" if source["id"].startswith("SEEDB2") else source["identity"]["doi"]
    splits = grouped_split([group(source) for source in sources], "cleareval-primary-families-v1")
    cases, labels = [], []
    for source in sources:
        snapshot = source["snapshot"]
        raw = bound_read(root / snapshot["raw_path"], snapshot["raw_sha256"])
        body_bytes = bound_read(root / snapshot["text_path"], snapshot["text_sha256"])
        body = body_bytes.decode("utf-8")
        for passage in source["passages"]:
            quote = passage["quote"]
            if body[passage["start"]:passage["end"]] != quote or sha(quote.encode("utf-8")) != passage["sha256"]:
                raise ValueError("Primary source passage does not match frozen full body")
            key = "primary-literal:" + source["id"] + ":" + passage["id"]
            payload = {"protocol": quote,
                       "requirements": ["Determine whether this candidate passage is literally supported by the named publication/version; do not infer wet-lab success."],
                       "source_cards": [{"id": source["id"], "identity": source["identity"],
                                         "body": body, "body_sha256": snapshot["text_sha256"]}]}
            cases.append({"id": key, "task_id": "PUBLISHED_LITERAL_SOURCE_CONSISTENCY",
                          "source_group": group(source), "split": splits[group(source)],
                          "input": payload, "input_sha256": json_hash(payload), "label_key": key})
            labels.append({"label_key": key, "label_origin": "PUBLISHED_LITERAL_PASSAGE",
                           "labels": {"literal_source_consistent": True},
                           "encoding_origin": "ASSISTANT_DEFINED_LITERAL_MATCH_TASK",
                           "independent_scientific_task_gold": False,
                           "provenance": {"source_id": source["id"], "url": source["identity"]["url"],
                                          "source_version": source["identity"]["version"],
                                          "raw_sha256": sha(raw), "body_sha256": sha(body_bytes),
                                          "start": passage["start"], "end": passage["end"],
                                          "quote_sha256": passage["sha256"]},
                           "scientific_applicability": None, "wet_lab_success": None})
    audit_input_separation(cases, labels)
    return cases, labels, {"published_sources": len(sources), "original_publication_families": len(splits),
                           "literal_cases": len(cases), "positive_only": True,
                           "scientific_necessity_validation": "NOT_ESTABLISHED",
                           "source_split": splits}


def write_bundle(workspace, upstream, out):
    out = Path(out)
    if out.exists():
        raise ValueError("Material output exists; refusing overwrite")
    cases, fragments, labels, err_audit = err_materials(upstream)
    primary, primary_labels, primary_audit = primary_materials(workspace)
    out.mkdir(parents=True, exist_ok=False)
    def jsonl(name, rows):
        (out / name).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                               encoding="utf-8", newline="\n")
    jsonl("cases.jsonl", cases)
    jsonl("official_information_fragments.jsonl", fragments)
    jsonl("labels.jsonl", labels)
    jsonl("published_literal_cases.jsonl", primary)
    jsonl("published_literal_labels.jsonl", primary_labels)
    manifest = {
        "schema_version": "same-information-published-materials-v1",
        "ERR": err_audit, "published_primary": primary_audit,
        "public_input_fields": ["id", "task_id", "source_group", "split", "input", "input_sha256", "label_key"],
        "same_information_rule": "ALL_METHODS_RECEIVE_IDENTICAL_CANONICAL_INPUT_ONLY",
        "label_files_for_metrics_only": ["labels.jsonl", "published_literal_labels.jsonl"],
        "gold_exposed_to_teacher": False,
        "expert_consistency": None, "scientific_accuracy": None,
        "synthetic_assistant_quality_labels_used_as_independent_gold": False,
        "builder_code_sha256": sha(Path(__file__).read_bytes()),
        "files": {path.name: {"sha256": sha(path.read_bytes()), "bytes": path.stat().st_size}
                  for path in out.iterdir() if path.is_file()},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8", newline="\n")
    return manifest


FACT_SPECS = (
    {"id": "FDISCO_BEST_EGFP_ASSAY", "source": "FDISCO_SCIADV_2019",
     "question": "Extract the temperature and pH of the group explicitly reported as having the best EGFP fluorescence preservation in the in-vitro comparison. Retain the assay scope.",
     "pattern": r"The\s+(\d+)\s*°C/pH\s+(\d+(?:\.\d+)?)\s+group demonstrated the best EGFP fluorescence preservation",
     "fields": ("temperature_C", "pH"), "types": ("number", "number")},
    {"id": "SEEDB2G_IMMERSION_RI", "source": "SEEDB2_PROTOCOL_2018",
     "question": "Extract the stated immersion medium and refractive index for SeeDB2G; do not conflate it with SeeDB2S or SeeDB.",
     "pattern": r"Use\s+(glycerol)\s*\(Refractive index\s*=\s*(\d+(?:\.\d+)?)\)\s*for\s*SeeDB2G",
     "fields": ("immersion_medium", "refractive_index"), "types": ("text", "number")},
    {"id": "SEEDB2S_IMMERSION_RI", "source": "SEEDB2_PROTOCOL_2018",
     "question": "Extract the stated immersion medium and refractive index for SeeDB2S; retain the exact method variant.",
     "pattern": r"(oil)\s*\(Refractive index\s*=\s*(\d+(?:\.\d+)?);\s*Type F\)\s*for\s*SeeDB2S",
     "fields": ("immersion_medium", "refractive_index"), "types": ("text", "number")},
    {"id": "MACS_REPORTED_DII_PRESERVATION", "source": "MACS_ADVSCI_2020",
     "question": "Extract the tracer and the author's exact qualitative description of its fluorescence preservation by MACS. Do not extrapolate to other dyes.",
     "pattern": r"MACS can preserve the fluorescence of\s+(DiI)\s+(fairly well)",
     "fields": ("tracer", "reported_qualifier"), "types": ("text", "text")},
    {"id": "FDISCO_REPORTED_INCOMPATIBLE_TRACERS", "source": "FDISCO_SCIADV_2019",
     "question": "Extract the specific tracers named in the sentence reporting unchanged incompatibility in FDISCO. Retain that negation and scope.",
     "pattern": r"did not change the incompatibility with some specific tracers\s*\(such as\s+(DiI)\s+and\s+(SYTO 16)\)",
     "fields": ("named_tracer_1", "named_tracer_2"), "types": ("text", "text")},
    {"id": "FRUIT_REPORTED_EXPANSION_FACTOR", "source": "FRUIT_FRONTNEUROANAT_2015",
     "question": "Extract the substance and stated concentration qualifier that the authors concluded mainly explained FRUIT-mediated tissue expansion.",
     "pattern": r"FRUIT-mediated tissue expansion was mainly due to the\s+(high concentration)\s+of\s+(urea)",
     "fields": ("concentration_qualifier", "substance"), "types": ("text", "text")},
)


def build_parameter_facts(workspace, out_dir):
    """Exact author-stated values, not assistant scientific-quality judgments."""
    root, out = Path(workspace), Path(out_dir)
    if out.exists():
        raise ValueError("Published fact output already exists")
    registry = json.loads((root / "KnowledgeBase/source_registry.json").read_text(encoding="utf-8"))
    by_id = {source["id"]: source for source in registry["sources"]}
    families = ["SEEDB2_PROTOCOL_VERSION_FAMILY" if row["source"].startswith("SEEDB2")
                else by_id[row["source"]]["identity"]["doi"] for row in FACT_SPECS]
    splits = grouped_split(families, "cleareval-primary-families-v1")
    cases, labels = [], []
    for spec, family in zip(FACT_SPECS, families):
        source = by_id[spec["source"]]
        snapshot = source["snapshot"]
        body = bound_read(root / snapshot["text_path"], snapshot["text_sha256"]).decode("utf-8")
        bound_read(root / snapshot["raw_path"], snapshot["raw_sha256"])
        matches = list(re.finditer(spec["pattern"], body))
        unique = {match.groups() for match in matches}
        if len(unique) != 1:
            raise ValueError("Author-stated value is missing or ambiguous: " + spec["id"])
        match = matches[0]
        fields = {}
        supports = {}
        for index, (field, kind) in enumerate(zip(spec["fields"], spec["types"]), 1):
            raw = match.group(index)
            fields[field] = float(raw) if kind == "number" else raw
            supports[field] = {"start": match.start(index), "end": match.end(index), "quote": raw,
                               "transform": "DECIMAL_TO_NUMBER" if kind == "number" else "IDENTITY"}
        cards = [{"id": source["id"], "identity": source["identity"], "body": body,
                  "body_sha256": snapshot["text_sha256"]}]
        if spec["source"].startswith("SEEDB2"):
            correction = by_id["SEEDB2_CORRECTION_2018"]
            c = correction["snapshot"]
            correction_body = bound_read(root / c["text_path"], c["text_sha256"]).decode("utf-8")
            cards.append({"id": correction["id"], "identity": correction["identity"],
                          "body": correction_body, "body_sha256": c["text_sha256"]})
        payload = {"protocol": body, "question": spec["question"],
                   "requirements": ["Return exact reported fields as JSON; this is a publication-consistency task, not a success prediction."],
                   "requested_fields": list(spec["fields"]), "source_cards": cards}
        key = "published-parameter:" + spec["id"]
        cases.append({"id": key, "task_id": "PUBLISHED_STATED_FACT_EXTRACTION",
                      "source_group": family, "split": splits[family], "input": payload,
                      "input_sha256": json_hash(payload), "label_key": key})
        labels.append({"label_key": key, "label_origin": "PUBLISHED_AUTHOR_STATED_VALUE",
                       "labels": fields, "field_support": supports,
                       "encoding_origin": "ASSISTANT_DEFINED_REGEX_OF_LITERAL_PUBLISHED_VALUES",
                       "scientific_quality_gold": False, "wet_lab_success": None,
                       "scientific_applicability": None,
                       "provenance": {"source_id": source["id"], "url": source["identity"]["url"],
                                      "version": source["identity"]["version"],
                                      "body_sha256": snapshot["text_sha256"],
                                      "context_start": match.start(), "context_end": match.end(),
                                      "context_quote": match.group(), "extraction_pattern": spec["pattern"]}})
    audit_input_separation(cases, labels)
    out.mkdir(parents=True, exist_ok=False)
    for name, rows in (("cases.jsonl", cases), ("labels.jsonl", labels)):
        (out / name).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                               encoding="utf-8", newline="\n")
    manifest = {"schema_version": "published-stated-facts-v1", "cases": len(cases),
                "publication_families": len(splits), "source_split": splits,
                "values_are_independent_published_statements": True,
                "task_and_encoding_are_assistant_authored": True,
                "wet_lab_success": None, "scientific_quality_gold": False,
                "label_file_for_metrics_only": "labels.jsonl", "expert_consistency": None,
                "files": {p.name: {"sha256": sha(p.read_bytes()), "bytes": p.stat().st_size}
                          for p in out.iterdir()}}
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8", newline="\n")
    return manifest
