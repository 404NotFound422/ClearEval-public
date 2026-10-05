"""Pure engineering counterexamples; fixture statements are not published gold."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.construct_validity.contract import digest
from experiments.construct_validity.fidelity import text_hash
from experiments.construct_validity.task_state import INITIAL_FIXATION
import oeq_workflow_diagnostics as workflow


class WorkflowDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        (self.workspace / "KnowledgeBase").mkdir()
        self.source_text = "Fixture recommendation for CUBIC-R+. Avoid storage at 4 C because the medium may crystallize."
        self.version = "synthetic-fixture-v1-not-published-gold"
        self.url = "https://example.org/engineering-fixture"
        self.source_path = self.workspace / "KnowledgeBase/source-fixture.txt"
        self.source_path.write_text(self.source_text, encoding="utf-8", newline="\n")
        self.registry = {"sources": [self.source()]}
        self.write_json("KnowledgeBase/source_registry.json", self.registry)
        self.write_json("KnowledgeBase/method_ri_ref.json", {"ri_ref": {"CUBIC": {}, "MACS": {}}})
        self.rules = {"schema_version": "source-condition-rules-v1", "rules": []}
        self.write_json("KnowledgeBase/source_condition_rules.json", self.rules)
        self.question = {"id": "Q-fixture", "question": "Provide one complete method within the stated scope."}
        self.protocol = "Chosen Method: CUBIC\nAn explicitly declared operation."

    def write_json(self, name, value):
        (self.workspace / name).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8", newline="\n")

    def source(self):
        return {
            "id": "FIXTURE", "method": "CUBIC",
            "identity": {"url": self.url, "version": self.version, "publication_status": "CURRENT"},
            "snapshot": {
                "text_path": "KnowledgeBase/source-fixture.txt",
                "text_sha256": hashlib.sha256(self.source_path.read_bytes()).hexdigest(),
                "identity_url": self.url, "version": self.version,
            },
            "passages": [{"id": "P1", "start": 0, "end": len(self.source_text),
                          "quote": self.source_text, "sha256": text_hash(self.source_text)}],
        }

    def build(self, question=None, protocol=None):
        return workflow.build_workflow_diagnostics(
            self.question if question is None else question,
            self.protocol if protocol is None else protocol, self.workspace)

    @staticmethod
    def rehash(value):
        value["diagnostics_sha256"] = digest({key: item for key, item in value.items()
                                             if key != "diagnostics_sha256"})

    def add_storage_rule(self):
        self.rules["rules"] = [{
            "id": "FIXTURE_STORAGE", "type": "AUTHOR_RECOMMENDATION",
            "condition_type": "EXPLICIT_IMMERSED_STORAGE_TEMPERATURE",
            "decision_policy": "ADVISORY_ONLY_NEVER_CHANGE_REQUIREMENT_STATE",
            "medium_family": "CUBIC-R+", "method_key": "CUBIC",
            "source_id": "FIXTURE", "source_sha256": text_hash(self.source_text),
            "source_version": self.version, "source_passage_ids": ["P1"],
            "source_guidance_span": {"start": 0, "end": len(self.source_text), "quote": self.source_text},
            "avoid_temperature_C": 4,
            "source_procedure_scope": "Synthetic engineering storage relation fixture",
            "source_scope_limit": "Not a published or experimental success label",
        }]
        self.write_json("KnowledgeBase/source_condition_rules.json", self.rules)

    def test_real_context_build_is_compact_and_input_bound(self):
        result = self.build()
        self.assertTrue(workflow.is_workflow_diagnostics_complete(result, self.question, self.protocol))
        self.assertEqual(result["question_sha256"], digest(self.question))
        self.assertEqual(result["protocol_sha256"], text_hash(self.protocol))
        source = result["source_inventory"][0]
        self.assertEqual(source["id"], "FIXTURE")
        self.assertEqual(source["version"], self.version)
        self.assertTrue(source["selected"])
        self.assertEqual(source["snapshot_file_sha256"], self.registry["sources"][0]["snapshot"]["text_sha256"])
        encoded = json.dumps(result)
        self.assertNotIn(self.source_text, encoded)
        self.assertNotIn('"prompt"', encoded)
        self.assertNotIn('"source_document"', encoded)
        self.assertNotIn('"source_record_catalog"', encoded)
        self.assertIsNone(result["expert_consistency"])

    def test_required_function_keywords_do_not_fake_grounded_action(self):
        question = {"question": "样本尚未固定，请在本方案包括固定步骤。"}
        protocol = "Chosen Method: CUBIC\nPerform initial fixation."
        result = self.build(question, protocol)
        functions = [item["diagnostic"] for item in result["task_function_diagnostics"]
                     if item["diagnostic"]["required_function"] == INITIAL_FIXATION]
        self.assertEqual(len(functions), 1)
        self.assertEqual(functions[0]["execution_obligation"], "REQUIRED")
        self.assertEqual(functions[0]["status"], "UNRESOLVED")
        self.assertIn("LEGACY_OR_UNVERIFIED_EXTRACTION", functions[0]["guards"])
        self.assertFalse(functions[0]["action_presence_certified"])
        self.assertEqual(result["scientific_status"], "U")

    def test_completed_fixation_is_applicability_only_not_repeat_prohibition(self):
        result = self.build({"question": "初始固定已完成。"})
        functions = [item["diagnostic"] for item in result["task_function_diagnostics"]
                     if item["diagnostic"]["required_function"] == INITIAL_FIXATION]
        self.assertEqual(len(functions), 1)
        self.assertEqual(functions[0]["execution_obligation"], "NOT_REQUIRED")
        self.assertTrue(functions[0]["applicability_only"])
        self.assertFalse(functions[0]["repetition_prohibited"])
        self.assertFalse(functions[0]["action_presence_certified"])
        self.assertTrue(workflow.is_workflow_diagnostics_complete(result))

    def test_absence_of_warning_does_not_certify_science(self):
        result = self.build()
        conditions = result["source_condition_diagnostics"]
        self.assertEqual(conditions["findings"], [])
        self.assertEqual(conditions["absence_of_warning_interpretation"],
                         "NO_WARNING_IS_NOT_SCIENTIFIC_COMPLIANCE_OR_SUCCESS")
        self.assertEqual(result["technical_status"], "VALID")
        self.assertEqual(result["scientific_status"], "U")
        for field in ("scientific_gold", "expert_consistency", "wet_lab_success"):
            self.assertIsNone(result[field])

    def test_local_source_warning_preserves_bound_scope_and_unknown_science(self):
        self.add_storage_rule()
        protocol = "Chosen Method: CUBIC\nStore the sample in CUBIC-R+(M) (Temperature: 4 C)"
        result = self.build(protocol=protocol)
        conditions = result["source_condition_diagnostics"]
        self.assertEqual(conditions["potential_conflict_count"], 1)
        finding = conditions["findings"][0]
        self.assertFalse(finding["changes_requirement_states"])
        self.assertEqual(finding["source_proof"]["source_id"], "FIXTURE")
        self.assertIn("NON_GEL_SOURCE_SCOPE_NOT_FULLY_ESTABLISHED", finding["source_scope_guards"])
        self.assertEqual(result["scientific_status"], "U")
        self.assertTrue(workflow.is_workflow_diagnostics_complete(result, self.question, protocol))

    def test_legacy_cce_and_prose_numbers_are_not_objective_measurements(self):
        question = {**self.question, "legacy_CCE": 3, "scores": {"time": 3, "cost": 3}}
        result = self.build(question, "Chosen Method: CUBIC\nTime: 24 h. Cost: 5 units. RI: 1.51.")
        objectives = result["objective_diagnostics"]
        self.assertEqual(objectives["status"], "U")
        self.assertEqual(objectives["relationship"], "UNRESOLVED")
        self.assertIsNone(objectives["measurements"])
        self.assertIsNone(objectives["constraints"])
        self.assertIsNone(objectives["no_hard_constraints_declared"])
        self.assertIn("TYPED_AUDITED_OBJECTIVE_MEASUREMENTS_NOT_SUPPLIED", objectives["reasons"])

    def test_single_declared_method_does_not_prove_complete_candidate(self):
        result = self.build(protocol="Chosen Method: CUBIC\nComplete all needed work.")
        candidate = result["candidate_necessity_diagnostics"]
        self.assertEqual(candidate["status"], "U")
        self.assertIsNone(candidate["complete_candidate_boundaries"])
        self.assertIsNone(candidate["necessary_requirements_satisfied"])
        self.assertIn("COMPLETE_CANDIDATE_BOUNDARIES_NOT_AUDITED", candidate["reasons"])

    def test_each_missing_required_resource_is_visible_failure(self):
        for name in workflow._RESOURCE_PATHS:
            path = self.workspace / name
            content = path.read_bytes()
            path.unlink()
            try:
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, "resource missing"):
                    self.build()
            finally:
                path.write_bytes(content)

    def test_missing_declared_source_snapshot_is_visible_failure(self):
        self.source_path.unlink()
        with self.assertRaisesRegex(ValueError, "Source snapshot missing"):
            self.build()

    def test_changed_source_bytes_are_rejected(self):
        self.source_path.write_text("Changed fulltext with old hash.", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Source snapshot hash mismatch"):
            self.build()

    def test_false_source_passage_is_rejected(self):
        self.registry["sources"][0]["passages"][0]["quote"] = "A false quote"
        self.write_json("KnowledgeBase/source_registry.json", self.registry)
        with self.assertRaises(ValueError):
            self.build()

    def test_snapshot_path_outside_workspace_is_rejected(self):
        self.registry["sources"][0]["snapshot"]["text_path"] = "../outside.txt"
        self.write_json("KnowledgeBase/source_registry.json", self.registry)
        with self.assertRaisesRegex(ValueError, "outside workspace"):
            self.build()

    def test_malformed_input_and_nonfinite_metadata_are_visible_failures(self):
        for question, protocol in [
            ([], self.protocol), ({}, self.protocol), ({"question": []}, self.protocol),
            ({"question": " "}, self.protocol), (self.question, ""), (self.question, None),
            ({**self.question, "value": float("nan")}, self.protocol),
            ({**self.question, "value": object()}, self.protocol),
            ({**self.question, 1: "not a JSON key"}, self.protocol),
        ]:
            with self.subTest(question_type=type(question).__name__, protocol_type=type(protocol).__name__):
                with self.assertRaises(ValueError):
                    workflow.build_workflow_diagnostics(question, protocol, self.workspace)

    def test_question_text_and_metadata_changes_invalidate_input_binding(self):
        result = self.build()
        self.assertFalse(workflow.is_workflow_diagnostics_complete(
            result, {**self.question, "question": "Another task."}, self.protocol))
        self.assertFalse(workflow.is_workflow_diagnostics_complete(
            result, {**self.question, "marker_query_targets": [{"structure_or_cell_subtype": "other"}]}, self.protocol))

    def test_unchanged_protocol_bytes_not_trimmed_or_normalized(self):
        protocol = "  " + self.protocol + "\r\n"
        result = self.build(protocol=protocol)
        self.assertEqual(result["protocol_sha256"], text_hash(protocol))
        self.assertTrue(workflow.is_workflow_diagnostics_complete(result, self.question, protocol))
        self.assertFalse(workflow.is_workflow_diagnostics_complete(result, self.question, protocol.strip()))

    def test_artifact_tamper_and_stale_schema_are_incomplete(self):
        result = self.build()
        changed = deepcopy(result)
        changed["source_inventory"][0]["version"] = "tampered"
        self.assertFalse(workflow.is_workflow_diagnostics_complete(changed))
        changed = deepcopy(result)
        changed["schema_version"] = "older-sidecar"
        self.rehash(changed)
        self.assertFalse(workflow.is_workflow_diagnostics_complete(changed))

    def test_self_rehash_does_not_allow_scientific_pass_or_unbound_objectives(self):
        original = self.build()
        for field, value in [
            ("scientific_status", "SATISFIED"),
            ("objective_diagnostics", {"status": "SATISFIED", "measurements": {"time": 24}}),
            ("candidate_necessity_diagnostics", {"status": "SATISFIED"}),
            ("expert_consistency", 1),
        ]:
            changed = deepcopy(original)
            changed[field] = value
            self.rehash(changed)
            with self.subTest(field=field):
                self.assertFalse(workflow.is_workflow_diagnostics_complete(changed))

    def test_broken_nested_binding_is_rejected_even_after_rehash(self):
        changed = self.build()
        changed["input_binding"]["protocol_sha256"] = "0" * 64
        self.rehash(changed)
        self.assertFalse(workflow.is_workflow_diagnostics_complete(changed))

    def test_dependency_code_change_invalidates_artifact(self):
        result = self.build()
        changed = deepcopy(result["implementation_hashes"])
        changed["oeq_workflow_diagnostics.py"] = "0" * 64
        with patch.object(workflow, "_implementation_hashes", return_value=changed):
            self.assertFalse(workflow.is_workflow_diagnostics_complete(result))

    def test_version_change_updates_inventory_and_context_binding(self):
        original = self.build()
        self.registry["sources"][0]["identity"]["version"] = "fixture-v2"
        self.registry["sources"][0]["snapshot"]["version"] = "fixture-v2"
        self.write_json("KnowledgeBase/source_registry.json", self.registry)
        changed = self.build()
        self.assertNotEqual(original["source_inventory_sha256"], changed["source_inventory_sha256"])
        self.assertNotEqual(original["resource_binding_sha256"], changed["resource_binding_sha256"])
        self.assertEqual(changed["source_inventory"][0]["version"], "fixture-v2")
        self.assertTrue(workflow.is_workflow_diagnostics_complete(changed))

    def test_metadata_only_reference_is_not_promoted_to_fulltext_evidence(self):
        self.registry["sources"].append({
            "id": "UNAVAILABLE", "identity": {"url": "https://example.org/unavailable", "version": "fixture-meta"},
            "snapshot": None, "passages": [],
        })
        self.write_json("KnowledgeBase/source_registry.json", self.registry)
        result = self.build()
        self.assertEqual([source["id"] for source in result["source_inventory"]], ["FIXTURE"])
        self.assertEqual(result["metadata_only_source_inventory"][0]["status"], "METADATA_ONLY_NOT_SOURCE_EVIDENCE")
        self.assertTrue(workflow.is_workflow_diagnostics_complete(result))

    def test_repeat_build_is_deterministic_without_mutating_original_inputs(self):
        question = deepcopy(self.question)
        original = deepcopy(question)
        first = self.build(question)
        second = self.build(question)
        self.assertEqual(question, original)
        self.assertEqual(first, second)

    def test_large_fulltext_stays_out_of_compact_sidecar(self):
        self.source_text += "\n" + "Unselected fixture fulltext padding. " * 30000
        self.source_path.write_text(self.source_text, encoding="utf-8", newline="\n")
        self.registry["sources"][0]["snapshot"]["text_sha256"] = hashlib.sha256(self.source_path.read_bytes()).hexdigest()
        # Keep a small genuine locator, rather than turning the complete source
        # into a million-character quotation in the diagnostic fixture.
        self.write_json("KnowledgeBase/source_registry.json", self.registry)
        result = self.build()
        self.assertGreater(len(self.source_text), 1_000_000)
        self.assertLess(len(json.dumps(result, ensure_ascii=False)), 25_000)
        self.assertNotIn("Unselected fixture fulltext padding.", json.dumps(result))
        self.assertTrue(workflow.is_workflow_diagnostics_complete(result))

    def test_duplicate_keys_and_nonfinite_resource_json_are_rejected(self):
        path = self.workspace / "KnowledgeBase/source_condition_rules.json"
        for content in [
            '{"schema_version":"source-condition-rules-v1","rules":[],"rules":[]}',
            '{"schema_version":"source-condition-rules-v1","rules":[],"ignored":NaN}',
        ]:
            path.write_text(content, encoding="utf-8")
            with self.subTest(content=content), self.assertRaises(ValueError):
                self.build()

    def test_empty_fulltext_inventory_is_not_silent_unknown_success(self):
        self.registry["sources"] = [{
            "id": "METADATA", "identity": {"url": self.url, "version": self.version},
            "passages": [], "snapshot": None,
        }]
        self.write_json("KnowledgeBase/source_registry.json", self.registry)
        with self.assertRaisesRegex(ValueError, "No frozen fulltext source evidence"):
            self.build()

    def test_resource_change_during_context_build_is_visible_failure(self):
        original = workflow.oeq_scientific.build_context

        def change_after_build(*args, **kwargs):
            context = original(*args, **kwargs)
            self.write_json("KnowledgeBase/method_ri_ref.json", {"ri_ref": {"OTHER": {}}})
            return context

        with patch.object(workflow.oeq_scientific, "build_context", side_effect=change_after_build):
            with self.assertRaisesRegex(ValueError, "resources changed during audit"):
                self.build()

    def test_self_rehashed_source_scientific_certification_is_rejected(self):
        original = self.build()
        for field in ("scientific_validation", "independent_scientific_truth"):
            for value in (True, False, "CERTIFIED"):
                changed = deepcopy(original)
                changed["source_condition_diagnostics"][field] = value
                self.rehash(changed)
                with self.subTest(field=field, value=value):
                    self.assertFalse(workflow.is_workflow_diagnostics_complete(changed))

    def test_missing_explicit_source_truth_null_is_incomplete(self):
        original = self.build()
        for field in ("scientific_validation", "independent_scientific_truth"):
            changed = deepcopy(original)
            del changed["source_condition_diagnostics"][field]
            self.rehash(changed)
            with self.subTest(field=field):
                self.assertFalse(workflow.is_workflow_diagnostics_complete(changed))

    def test_nested_source_proof_cannot_claim_scientific_gold(self):
        self.add_storage_rule()
        result = self.build(protocol="Chosen Method: CUBIC\nStore the sample in CUBIC-R+ (Temperature: 4 C)")
        result["source_condition_diagnostics"]["findings"][0]["source_proof"]["scientific_gold"] = True
        self.rehash(result)
        self.assertFalse(workflow.is_workflow_diagnostics_complete(result))

    def test_self_rehashed_task_gold_or_nonprovisional_state_is_rejected(self):
        original = self.build({"question": "样本尚未固定，请在本方案包括固定步骤。"})
        for field, value in (("scientific_gold", True), ("provisional", False)):
            changed = deepcopy(original)
            changed["task_state_audit"][field] = value
            self.rehash(changed)
            with self.subTest(field=field):
                self.assertFalse(workflow.is_workflow_diagnostics_complete(changed))
        changed = deepcopy(original)
        changed["task_state_audit"]["functions"][INITIAL_FIXATION]["scientific_truth"] = True
        self.rehash(changed)
        self.assertFalse(workflow.is_workflow_diagnostics_complete(changed))

    def test_required_function_forged_satisfied_is_rejected_without_protocol(self):
        original = self.build({"question": "样本尚未固定，请在本方案包括固定步骤。"})
        self.assertTrue(workflow.is_workflow_diagnostics_complete(original))
        for field, value in (
            ("status", "SATISFIED"), ("guards", []),
            ("action_evidence", [{"quote": "invented action"}]),
            ("applicability_only", True),
        ):
            changed = deepcopy(original)
            changed["task_function_diagnostics"][0]["diagnostic"][field] = value
            self.rehash(changed)
            with self.subTest(field=field):
                self.assertFalse(workflow.is_workflow_diagnostics_complete(changed))

    def test_not_required_local_satisfied_remains_valid_and_exact(self):
        question = {"question": "初始固定已完成。"}
        original = self.build(question)
        value = original["task_function_diagnostics"][0]["diagnostic"]
        self.assertEqual(value["status"], "SATISFIED")
        self.assertTrue(value["applicability_only"])
        self.assertFalse(value["action_presence_certified"])
        self.assertTrue(workflow.is_workflow_diagnostics_complete(original))
        self.assertTrue(workflow.is_workflow_diagnostics_complete(original, question, self.protocol))
        for field, forged in (("repetition_prohibited", True), ("status", "UNRESOLVED")):
            changed = deepcopy(original)
            changed["task_function_diagnostics"][0]["diagnostic"][field] = forged
            self.rehash(changed)
            with self.subTest(field=field):
                self.assertFalse(workflow.is_workflow_diagnostics_complete(changed))

    def test_task_requirement_rule_cannot_disagree_with_task_state(self):
        changed = self.build({"question": "样本尚未固定，请在本方案包括固定步骤。"})
        for requirement in changed["provisional_r_contracts"]:
            rule = requirement.get("literal_rule")
            if isinstance(rule, dict) and rule.get("type") == "TASK_INITIAL_FUNCTION":
                rule["state_audit"]["execution_obligation"] = "NOT_REQUIRED"
        self.rehash(changed)
        self.assertFalse(workflow.is_workflow_diagnostics_complete(changed))

    def test_missing_task_scientific_null_and_provisional_mark_are_rejected(self):
        original = self.build({"question": "初始固定已完成。"})
        for field in ("scientific_truth", "provisional"):
            changed = deepcopy(original)
            del changed["task_state_audit"]["functions"][INITIAL_FIXATION][field]
            self.rehash(changed)
            with self.subTest(field=field):
                self.assertFalse(workflow.is_workflow_diagnostics_complete(changed))


if __name__ == "__main__":
    unittest.main()
