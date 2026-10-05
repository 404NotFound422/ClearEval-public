"""Production-entry engineering tests, synthetic data only; no model clients.

The OEQ loader is selected from its actual AST so importing the legacy entry
cannot create clients or read user configuration. Builder imports only stdlib
and the synthetic KB in a temporary workspace.
"""
import ast
from contextlib import contextmanager
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from evaluation_contract import DEMAND_AXES, FixedDemandRegistry, json_hash, sha256_file
from evaluator_integrity import parse_judge_object
from models.Model_Loader import read_model_config
from oeq_preflight import run_preflight

ROOT = Path(__file__).resolve().parents[1]


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+chr(10),encoding="utf-8")


@contextmanager
def cwd(path):
    previous=Path.cwd()
    os.chdir(path)
    try: yield
    finally: os.chdir(previous)


class WorkspaceFixture:
    def __init__(self,root):
        self.root=root
        self.question={"question_id":1,"question":"SYNTHETIC ENGINEERING ONLY: keep stated label.",
                       "tissue_hierarchy_from_tissue_xlsx":{"tissue_inferred":"synthetic","tissue_tier_code":"T",
                                                            "tissue_tier_label":"synthetic size"},
                       "marker_query_targets":[]}
        self.questions=[self.question]
        self.vectors={"1":{axis:{"target":0,"weight":0} for axis in DEMAND_AXES}}
        self.question_path=root/"dataset/Q+AR/src/question_final.json"
        self.demand_path=root/"dataset/Q+AR/src/demand_vectors_all.json"
        self.manifest_path=Path(str(self.demand_path)+".manifest.json")
        write(self.question_path,self.questions)
        write(self.demand_path,self.vectors)
        write(root/"bound_questions.json",self.questions)
        write(self.manifest_path,{"hash_format":"canonical-json-sha256-v1","questions_sha256":json_hash(self.questions),
                                 "demand_vectors_sha256":json_hash(self.vectors),"questions_file":"bound_questions.json",
                                 "binding_note":"Synthetic engineering values, no scientific labels"})
        self.row={"lookup_key":"CUBIC|T","method":"CUBIC","tier_code":"T","clearing_time_min_h":1,
                  "clearing_time_median_h":2,"clearing_time_max_h":3,"time_excludes_labeling":"yes",
                  "time_scope":"仅透明处理，不含染色与标记。","source_url":"https://example.org/synthetic"}
        self.time={"rows":[self.row],"lookup":{"CUBIC":{"T":self.row}}}
        values={"KnowledgeBase/tissue.json":[],
                "KnowledgeBase/method_fluro_compati.json":[{"method":"CUBIC","GFP":0.8}],
                "KnowledgeBase/time_kb.json":self.time,
                "KnowledgeBase/tissue_ri.json":{"tissue_ri_database":{"default_ri":1.48,"tissues":{},
                                                        "calibration_status":"LEGACY_HEURISTIC_NOT_CALIBRATED"}},
                "KnowledgeBase/method_ri_ref.json":{"ri_ref":{"CUBIC":{"ri":1.46,"primary_sample":"synthetic",
                                                                         "source":"SYNTHETIC ENGINEERING ONLY"}}},
                "KnowledgeBase/method_sigma_ri.json":{"sigma_ri":{}},
                "dataset/Q+AR/src/model_space_signed.json":{"methods":{"CUBIC":{"F_fp":1}}},
                "dataset/Q+AR/src/model_space.json":{"methods":{"CUBIC":{}}},
                "KnowledgeBase/source_registry.json":{"schema_version":"knowledge-source-registry-v1",
                    "sources":[{"id":"SYNTHETIC","snapshot":None,"grounding_status":"UNRESOLVED"}]},
                "KnowledgeBase/article_chunk/synthetic.json":{"claim":"SYNTHETIC ENGINEERING ONLY"},
                "dataset/Q+AR/src/standard_response.json":[],
                "config/synthetic_models.json":{"models":[{"name":" synthetic-local ","type":" Ollama ",
                                                           "model_name":" synthetic-fixture ",
                                                           "api_key":"SYNTHETIC_SENTINEL_DO_NOT_REPORT",
                                                           "base_url":"SYNTHETIC_PRIVATE_ENDPOINT_DO_NOT_REPORT"}]}}
        for relative,value in values.items():write(root/relative,value)
        for relative in ("dataset/Q+AR/src/restrict.py","prompts/eval_teacher_protocol_review.py"):
            path=root/relative;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text("# Synthetic resource presence only; never executed.\n",encoding="utf-8")

    def builder(self):
        spec=importlib.util.spec_from_file_location("synthetic_rag_builder_"+self.root.name,ROOT/"build_rag_context.py")
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.configure_sources(self.question_path,self.demand_path,self.manifest_path)
        return module

    def loader(self):
        names={"_load_rag_context_block"}
        tree=ast.parse((ROOT/"OEQ_run_grading_new.py").read_text(encoding="utf-8"))
        nodes=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names]
        if {node.name for node in nodes}!=names:raise AssertionError("Production RAG loader missing")
        registry=FixedDemandRegistry(self.question_path,self.demand_path,self.manifest_path)
        namespace={"Path":Path,"json":json,"RAG_CONTEXT_DIR":str(self.root/"dataset/Q+AR/rag_context"),
                   "_QUESTION_LIST":deepcopy(self.questions),"fixed_demands":lambda:registry,
                   "json_hash":json_hash,"sha256_file":sha256_file,"parse_judge_object":parse_judge_object,
                   "_RAG_BLOCK_CACHE":{},"QUESTION_FILE":str(self.question_path),
                   "DEMAND_PROFILE": "fixed", "DEMAND_FILE":str(self.demand_path),"DEMAND_MANIFEST":str(self.manifest_path)}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(ROOT/"OEQ_run_grading_new.py"),"exec"),namespace)
        return namespace

    def save_card(self,card):
        path=self.root/"dataset/Q+AR/rag_context/rag_context_1.json"
        write(path,card)
        return path


def isolated_cli(script, args, workspace):
    # -I alone is insufficient when a local ._pth explicitly lists ROOT.
    # Remove that path and assert the project is unavailable before the CLI runs.
    bootstrap = (
        "import importlib.util, runpy, socket, sys; from pathlib import Path\n"
        "root = Path(sys.argv[1]).resolve(); script = sys.argv[2]; args = sys.argv[3:]\n"
        "sys.path[:] = [p for p in sys.path if p and not Path(p).resolve().is_relative_to(root)]\n"
        "assert sys.flags.isolated\n"
        "assert importlib.util.find_spec('evaluation_contract') is None\n"
        "def fail_network(*args, **kwargs): raise AssertionError('CLI preflight attempted external network')\n"
        # Windows asyncio uses socket.connect internally to create its socketpair.
        "socket.create_connection = fail_network\n"
        "class NoProviders:\n"
        "    def find_spec(self, fullname, path=None, target=None):\n"
        "        if fullname.startswith('models.') and fullname != 'models.Model_Loader':\n"
        "            raise AssertionError('CLI preflight imported provider: ' + fullname)\n"
        "sys.meta_path.insert(0, NoProviders())\n"
        "sys.argv = [str(root / script)] + args\n"
        "runpy.run_path(sys.argv[0], run_name='__main__')\n"
    )
    return subprocess.run(
        [sys.executable, "-I", "-B", "-c", bootstrap, str(ROOT), script, *args],
        cwd=workspace, capture_output=True, text=True, encoding="utf-8",
        check=False, timeout=30,
    )


class PreflightTests(unittest.TestCase):
    def test_bound_question_and_kb_counts_are_read_only_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture=WorkspaceFixture(Path(tmp))
            result=run_preflight(fixture.root,require_model=False)
            self.assertTrue(result["technical_ready"])
            self.assertIsNone(result["scientific_ready"])
            self.assertEqual(result["network_requests"],0)
            self.assertEqual(result["coverage"]["questions"],1)
            self.assertEqual(result["coverage"]["time_rows"],1)
            self.assertEqual(result["coverage"]["compatibility_methods"],1)
            self.assertEqual(result["coverage"]["compatibility_cells_without_individual_source_bindings"],1)
            self.assertEqual(result["coverage"]["article_chunk_files"],1)
            self.assertEqual(result["coverage"]["source_registry_entries"],1)
            self.assertEqual(result["coverage"]["primary_snapshots_bound"],0)
            self.assertIn("PRIMARY_PASSAGES_PENDING",{issue["code"] for issue in result["issues"]})

    def test_current_question_must_match_demand_bound_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture=WorkspaceFixture(Path(tmp))
            revised=deepcopy(fixture.questions);revised[0]["question"]+=" changed same question_id"
            write(fixture.question_path,revised)
            result=run_preflight(fixture.root,require_model=False)
            self.assertFalse(result["technical_ready"])
            issue=next(i for i in result["issues"] if i["code"]=="QUESTION_DEMAND_VERSION_MISMATCH")
            self.assertEqual(issue["compatible_snapshot"],"bound_questions.json")
            self.assertEqual(result["coverage"]["fixed_demand_binding"],"MISMATCH")

    def test_time_scope_conflict_is_reported_without_scientific_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture=WorkspaceFixture(Path(tmp))
            fixture.row["time_scope"]="包括固定、染色步骤、洗涤和成像前平衡。"
            write(fixture.root/"KnowledgeBase/time_kb.json",fixture.time)
            result=run_preflight(fixture.root,require_model=False)
            self.assertEqual(result["coverage"]["time_scope_conflicts"],1)
            self.assertIn("TIME_SCOPE_CONFLICT",{i["code"] for i in result["issues"]})
            self.assertIsNone(result["scientific_ready"])

    def test_explicit_exclusion_is_not_false_scope_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture=WorkspaceFixture(Path(tmp))
            fixture.row["time_scope"]="仅透明处理，不包括固定、染色步骤、标记步骤。"
            write(fixture.root/"KnowledgeBase/time_kb.json",fixture.time)
            result=run_preflight(fixture.root,require_model=False)
            self.assertEqual(result["coverage"]["time_scope_conflicts"],0)

    def test_json_model_config_read_does_not_load_provider_or_report_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture=WorkspaceFixture(Path(tmp))
            with patch("models.Model_Loader.importlib.import_module",side_effect=AssertionError("No provider imports")):
                config=read_model_config(fixture.root/"config/synthetic_models.json")
                result=run_preflight(fixture.root,model_config="config/synthetic_models.json",require_model=True)
            self.assertEqual(config["models"][0]["name"],"synthetic-local")
            self.assertTrue(result["technical_ready"])
            rendered=json.dumps(result)
            self.assertNotIn("SYNTHETIC_SENTINEL_DO_NOT_REPORT",rendered)
            self.assertNotIn("SYNTHETIC_PRIVATE_ENDPOINT_DO_NOT_REPORT",rendered)
            self.assertEqual(result["network_requests"],0)

    def test_cli_runs_kb_only_without_client_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture=WorkspaceFixture(Path(tmp));out=fixture.root/"preflight.json"
            result=subprocess.run([sys.executable,"-B",str(ROOT/"oeq_preflight.py"),"--workspace",str(fixture.root),
                                   "--kb-only","--out",str(out)],capture_output=True,text=True,encoding="utf-8",check=False)
            self.assertEqual(result.returncode,0,result.stderr)
            report=json.loads(out.read_text(encoding="utf-8"))
            self.assertTrue(report["technical_ready"])
            self.assertIsNone(report["scientific_ready"])
            self.assertEqual(report["network_requests"],0)


    def test_preflight_cli_bootstraps_script_directory_in_isolated_interpreter(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = WorkspaceFixture(Path(tmp))
            result = isolated_cli("oeq_preflight.py", ["--workspace", tmp, "--kb-only"], fixture.root)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["technical_ready"])
            self.assertEqual(report["network_requests"], 0)
            self.assertIsNone(report["scientific_ready"])

    def test_oeq_cli_preflight_bootstraps_script_directory_without_clients(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = WorkspaceFixture(Path(tmp))
            result = isolated_cli(
                "OEQ_run_grading_new.py",
                ["--preflight-only", "--model-config", "config/synthetic_models.json"],
                fixture.root,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["technical_ready"])
            self.assertEqual(report["network_requests"], 0)
            self.assertIsNone(report["scientific_ready"])
            self.assertNotIn("SYNTHETIC_SENTINEL_DO_NOT_REPORT", result.stdout)
            self.assertNotIn("SYNTHETIC_PRIVATE_ENDPOINT_DO_NOT_REPORT", result.stdout)


class RagBindingTests(unittest.TestCase):
    def test_production_builder_card_can_be_read_by_production_loader(self):
        with tempfile.TemporaryDirectory() as tmp,cwd(Path(tmp)):
            fixture=WorkspaceFixture(Path(tmp));builder=fixture.builder()
            card=builder.build_one(deepcopy(fixture.question));fixture.save_card(card)
            namespace=fixture.loader()
            self.assertEqual(namespace["_load_rag_context_block"](1),card["prompt_block"])
            self.assertEqual(namespace["_load_rag_context_block"](1),card["prompt_block"])
            self.assertEqual(len(namespace["_RAG_BLOCK_CACHE"]),1)

    def test_builder_cannot_bind_old_demand_to_revised_same_id_question(self):
        with tempfile.TemporaryDirectory() as tmp,cwd(Path(tmp)):
            fixture=WorkspaceFixture(Path(tmp));builder=fixture.builder()
            changed=deepcopy(fixture.question);changed["question"]+=" revised"
            with self.assertRaises(ValueError):builder.build_one(changed)

    def test_builder_cannot_bind_old_demand_to_revised_metadata(self):
        with tempfile.TemporaryDirectory() as tmp,cwd(Path(tmp)):
            fixture=WorkspaceFixture(Path(tmp));builder=fixture.builder()
            changed=deepcopy(fixture.question);changed["tissue_hierarchy_from_tissue_xlsx"]["tissue_tier_code"]="OTHER"
            with self.assertRaises(ValueError):builder.build_one(changed)

    def test_builder_stale_loaded_kb_cannot_certify_new_disk_hash(self):
        with tempfile.TemporaryDirectory() as tmp,cwd(Path(tmp)):
            fixture=WorkspaceFixture(Path(tmp));builder=fixture.builder()
            builder.build_one(deepcopy(fixture.question))
            write(fixture.root/"KnowledgeBase/method_fluro_compati.json",[{"method":"CUBIC","GFP":0}])
            with self.assertRaisesRegex(ValueError,"Knowledge base changed"):
                builder.build_one(deepcopy(fixture.question))

    def test_builder_registry_changes_need_explicit_new_process(self):
        with tempfile.TemporaryDirectory() as tmp,cwd(Path(tmp)):
            fixture=WorkspaceFixture(Path(tmp));builder=fixture.builder()
            write(fixture.root/"KnowledgeBase/source_registry.json",{"sources":[]})
            with self.assertRaisesRegex(ValueError,"Knowledge base changed"):
                builder.build_one(deepcopy(fixture.question))

    def test_cached_loader_rechecks_question_after_same_id_revision(self):
        with tempfile.TemporaryDirectory() as tmp,cwd(Path(tmp)):
            fixture=WorkspaceFixture(Path(tmp));builder=fixture.builder()
            card=builder.build_one(deepcopy(fixture.question));fixture.save_card(card)
            namespace=fixture.loader();namespace["_load_rag_context_block"](1)
            namespace["_QUESTION_LIST"][0]["question"]+=" changed same id"
            with self.assertRaises(ValueError):namespace["_load_rag_context_block"](1)

    def test_cached_loader_rechecks_kb_file_version(self):
        with tempfile.TemporaryDirectory() as tmp,cwd(Path(tmp)):
            fixture=WorkspaceFixture(Path(tmp));builder=fixture.builder()
            card=builder.build_one(deepcopy(fixture.question));fixture.save_card(card)
            namespace=fixture.loader();namespace["_load_rag_context_block"](1)
            write(fixture.root/"KnowledgeBase/tissue.json",[{"synthetic_change":True}])
            with self.assertRaises(ValueError):namespace["_load_rag_context_block"](1)

    def test_old_unbound_card_is_rejected_even_after_valid_card_cached(self):
        with tempfile.TemporaryDirectory() as tmp,cwd(Path(tmp)):
            fixture=WorkspaceFixture(Path(tmp));builder=fixture.builder()
            card=builder.build_one(deepcopy(fixture.question));fixture.save_card(card)
            namespace=fixture.loader();namespace["_load_rag_context_block"](1)
            fixture.save_card({"question_id":1,"prompt_block":"old unbound block"})
            with self.assertRaises(ValueError):namespace["_load_rag_context_block"](1)

    def test_unknown_binding_schema_is_not_silently_migrated(self):
        with tempfile.TemporaryDirectory() as tmp,cwd(Path(tmp)):
            fixture=WorkspaceFixture(Path(tmp));builder=fixture.builder()
            card=builder.build_one(deepcopy(fixture.question))
            card["input_binding"]["schema_version"]="question-kb-rag-binding-v1"
            fixture.save_card(card)
            with self.assertRaises(ValueError):fixture.loader()["_load_rag_context_block"](1)

    def test_mutated_prompt_is_not_validated_by_file_cache_key(self):
        with tempfile.TemporaryDirectory() as tmp,cwd(Path(tmp)):
            fixture=WorkspaceFixture(Path(tmp));builder=fixture.builder()
            card=builder.build_one(deepcopy(fixture.question));fixture.save_card(card)
            namespace=fixture.loader();namespace["_load_rag_context_block"](1)
            card["prompt_block"]="Changed after frozen build; should not become trusted context"
            fixture.save_card(card)
            with self.assertRaises(ValueError):namespace["_load_rag_context_block"](1)


if __name__=="__main__":unittest.main()