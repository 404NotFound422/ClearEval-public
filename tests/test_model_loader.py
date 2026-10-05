"""Offline provider/configuration regressions; SDK doubles never make requests."""
import asyncio
import importlib
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from models.Model_Loader import ModelLoader, read_model_config
from models.Ollama_LLM import OllamaLLM, OllamaOutputError, LocalOllamaHTTPClient


class FakeClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        self.closed = False
        self.response = {"response": "complete protocol", "done": True, "done_reason": "stop", "eval_count": 7}

    def generate(self, **kwargs):
        self.calls.append((kwargs, threading.get_ident()))
        return self.response

    def close(self):
        self.closed = True


class ConfigTests(unittest.TestCase):
    def config_file(self, rows):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "models.json"
        path.write_text(json.dumps({"models": rows}), encoding="utf-8")
        return path

    def test_only_selected_adapter_imported_and_ollama_does_not_fall_through(self):
        path = self.config_file([
            {"name": " local ", "type": " Ollama ", "model_name": " model "},
            {"name": "openai_remote", "type": "api", "model_name": "unused"},
        ])
        calls = []
        def load(name):
            calls.append(name)
            return SimpleNamespace(OllamaLLM=lambda **kw: SimpleNamespace(**kw))
        with patch("models.Model_Loader.importlib.import_module", side_effect=load):
            result = ModelLoader(path).load_models(["local"])
        self.assertEqual(calls, ["models.Ollama_LLM"])
        self.assertEqual(result["local"].model_name, "model")
        self.assertEqual(result["local"].max_length, 8192)

    def test_whitespace_duplicate_name_rejected_before_provider_import(self):
        path = self.config_file([
            {"name": "same ", "type": "Ollama", "model_name": "m"},
            {"name": " same", "type": "Ollama", "model_name": "m2"},
        ])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            ModelLoader(path)

    def test_missing_selected_model_fails_before_provider_import(self):
        path = self.config_file([{"name": "local", "type": "Ollama", "model_name": "m"}])
        with patch("models.Model_Loader.importlib.import_module", side_effect=AssertionError("provider imported")):
            with self.assertRaisesRegex(ValueError, "absent"):
                ModelLoader(path).load_models(["not-configured"])

    def test_json_reads_need_no_provider_or_yaml(self):
        path = self.config_file([{"name": "local", "type": "Ollama", "model_name": "m"}])
        with patch.dict(sys.modules, {"yaml": None, "ollama": None}):
            self.assertEqual(read_model_config(path)["models"][0]["name"], "local")

    def test_api_dispatch_preserves_provider_kwargs(self):
        path = self.config_file([{
            "name": " openai_test ", "type": "api", "model_name": " model ",
            "api_key": "test-placeholder", "base_url": " https://example.invalid/v1 ",
            "temperature": 0, "max_tokens": 1234, "enable_thinking": False,
        }])
        calls = []
        def load(name):
            calls.append(name)
            return SimpleNamespace(OpenAILLM=lambda **kw: kw)
        with patch("models.Model_Loader.importlib.import_module", side_effect=load):
            result = ModelLoader(path).load_models()
        self.assertEqual(calls, ["models.OpenAI_Model"])
        self.assertEqual(result["openai_test"]["temperature"], 0)
        self.assertEqual(result["openai_test"]["max_tokens"], 1234)
        self.assertEqual(result["openai_test"]["model_name"], "model")

    def test_duplicate_json_keys_are_rejected(self):
        path = self.config_file([])
        path.write_text('{"models":[],"models":[]}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            ModelLoader(path)


    def test_ollama_context_and_seed_configuration_passthrough(self):
        path = self.config_file([
            {"name": "configured", "type": "Ollama", "model_name": "m", "num_ctx": 4096, "seed": 0},
            {"name": "defaults", "type": "Ollama", "model_name": "m"},
            {"name": "none", "type": "Ollama", "model_name": "m", "num_ctx": None, "seed": None},
        ])
        adapter = SimpleNamespace(OllamaLLM=lambda **kwargs: SimpleNamespace(**kwargs))
        with patch("models.Model_Loader.importlib.import_module", return_value=adapter):
            result = ModelLoader(path).load_models()
        self.assertEqual(result["configured"].num_ctx, 4096)
        self.assertEqual(result["configured"].seed, 0)
        self.assertFalse(hasattr(result["defaults"], "num_ctx"))
        self.assertFalse(hasattr(result["defaults"], "seed"))
        self.assertIsNone(result["none"].num_ctx)
        self.assertIsNone(result["none"].seed)


class OllamaTests(unittest.IsolatedAsyncioTestCase):
    def model(self, **kwargs):
        with patch("models.Ollama_LLM.importlib.import_module", return_value=SimpleNamespace(Client=FakeClient)):
            return OllamaLLM(" local-model ", transport="sdk", **kwargs)

    def test_missing_official_sdk_is_hard_failure(self):
        with patch("models.Ollama_LLM.importlib.import_module", side_effect=ImportError("missing")):
            with self.assertRaisesRegex(ImportError, "no mock output"):
                OllamaLLM("model", transport="sdk")

    async def test_async_response_matches_oeq_and_does_not_block_event_thread(self):
        model = self.model(max_length=100, temperature=0, timeout=17, host="http://localhost:11434")
        data = await model._acall("protocol request", stop=["END"])
        self.assertEqual(data["content"], "complete protocol")
        kwargs, worker = model.client.calls[0]
        self.assertNotEqual(worker, threading.get_ident())
        self.assertEqual(kwargs["options"], {"num_predict": 100, "temperature": 0, "stop": ["END"]})
        self.assertFalse(kwargs["stream"])
        self.assertEqual(model.client.kwargs["timeout"], 17)
        self.assertEqual(data["metadata"]["completion_tokens"], 7)
        await model.aclose()
        self.assertTrue(model.client.closed)

    def test_stdlib_transport_makes_real_rest_request_without_sdk(self):
        from unittest.mock import MagicMock
        body = MagicMock()
        body.__enter__.return_value.read.return_value = b'{"response":"real-rest-format","done":true,"done_reason":"stop"}'
        opener = MagicMock()
        opener.open.return_value = body
        with patch("models.Ollama_LLM.urllib.request.build_opener", return_value=opener), patch(
                "models.Ollama_LLM.importlib.import_module", side_effect=AssertionError("SDK import forbidden")):
            model = OllamaLLM("local", max_length=42, timeout=19)
            self.assertEqual(model._call("request"), "real-rest-format")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://localhost:11434/api/generate")
        data = json.loads(request.data)
        self.assertFalse(data["stream"])
        self.assertFalse(data["think"])
        self.assertEqual(data["options"]["num_predict"], 42)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 19)

    def test_stdlib_transport_rejects_remote_or_credential_origins(self):
        for origin in ("https://example.invalid", "http://user:password@localhost:11434", "http://localhost:11434?secret=1"):
            with self.subTest(origin=origin):
                with self.assertRaisesRegex(ValueError, "loopback"):
                    LocalOllamaHTTPClient(origin)

    def test_sync_text_interface_is_preserved(self):
        model = self.model()
        self.assertEqual(model._call("request"), "complete protocol")
        self.assertEqual(model.generate_with_params("request", max_length=42), "complete protocol")
        self.assertEqual(model.client.calls[-1][0]["options"]["num_predict"], 42)

    def test_configured_json_format_is_sent_and_validated(self):
        model = self.model(format="json", enable_thinking=False)
        model.client.response["response"] = '{"scores":{"value":1}}'
        self.assertEqual(json.loads(model._call("JSON request"))["scores"]["value"], 1)
        self.assertEqual(model.client.calls[-1][0]["format"], "json")
        self.assertFalse(model.client.calls[-1][0]["think"])
        model.client.response["response"] = '{"x":1,"x":2}'
        with self.assertRaisesRegex(OllamaOutputError, "Duplicate") as caught:
            model._call("JSON request")
        error = caught.exception
        self.assertEqual(error.provider_response, model.client.response)
        self.assertEqual(error.finish_reason, "stop")
        self.assertEqual(error.response_data["raw_content"], '{"x":1,"x":2}')
        self.assertEqual(error.response_data["content"], "")
        self.assertEqual(error.response_data["metadata"]["technical_status"], "FAILED")

    def test_incomplete_empty_and_truncated_responses_fail(self):
        model = self.model(max_length=8)
        for response in (
            {"response": "partial", "done": False},
            {"response": "partial", "done": True, "done_reason": "length"},
            {"response": "partial", "done": True, "eval_count": 8},
            {"response": "  ", "done": True, "done_reason": "stop"},
        ):
            with self.subTest(response=response):
                model.client.response = response
                with self.assertRaises(OllamaOutputError) as caught:
                    model._call("request")
                error = caught.exception
                self.assertEqual(error.provider_response, response)
                self.assertEqual(error.finish_reason, response.get("done_reason"))
                self.assertEqual(error.response_data["raw_content"], response["response"])
                self.assertEqual(error.response_data["content"], "")
                metadata = error.response_data["metadata"]
                self.assertEqual(metadata["technical_status"], "FAILED")
                self.assertEqual(metadata["provider_response"], response)
                self.assertEqual(metadata["done"], response.get("done"))
                self.assertEqual(metadata["finish_reason"], response.get("done_reason"))
                self.assertEqual(metadata["completion_tokens"], response.get("eval_count"))
        self.assertIsNone(OllamaOutputError("No provider response available").response_data)

    def test_optional_context_and_seed_defaults_and_explicit_overrides(self):
        for kwargs in ({}, {"num_ctx": None, "seed": None}):
            model = self.model(**kwargs)
            model._call("request")
            self.assertEqual(model.client.calls[-1][0]["options"], {"num_predict": 8192, "temperature": 0.1})
        model = self.model(num_ctx=4096, seed=0)
        model._call("request")
        options = model.client.calls[-1][0]["options"]
        self.assertEqual(options["num_ctx"], 4096)
        self.assertEqual(options["seed"], 0)
        model.generate_with_params("request", num_ctx=2048, seed=-7)
        options = model.client.calls[-1][0]["options"]
        self.assertEqual(options["num_ctx"], 2048)
        self.assertEqual(options["seed"], -7)
        self.assertEqual(model.num_ctx, 4096)
        self.assertEqual(model.seed, 0)

    def test_invalid_context_and_seed_fail_before_client_or_request(self):
        invalid = ({"num_ctx": 0}, {"num_ctx": -1}, {"num_ctx": True},
                   {"num_ctx": 2048.0}, {"num_ctx": "2048"},
                   {"seed": False}, {"seed": 1.0}, {"seed": "1"})
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs):
                with patch("models.Ollama_LLM.importlib.import_module", side_effect=AssertionError("SDK imported")):
                    with self.assertRaises(ValueError):
                        OllamaLLM("model", transport="sdk", **kwargs)
                model = self.model()
                with self.assertRaises(ValueError):
                    model._call("request", **kwargs)
                self.assertEqual(model.client.calls, [])

    def test_natural_stop_at_budget_is_not_mislabelled_as_truncation(self):
        model = self.model(max_length=7)
        self.assertEqual(model._call("request"), "complete protocol")

    def test_timeout_propagates_without_fake_response(self):
        model = self.model()
        with patch.object(model.client, "generate", side_effect=TimeoutError("request timed out")):
            with self.assertRaises(TimeoutError):
                model._call("request")

    def test_invalid_generation_options_do_not_initialize_clients(self):
        for kwargs in ({"max_length": 0}, {"max_length": True}, {"timeout": 0},
                       {"temperature": float("nan")}, {"enable_thinking": "false"}):
            with self.subTest(kwargs=kwargs):
                with patch("models.Ollama_LLM.importlib.import_module", side_effect=AssertionError("SDK imported")):
                    with self.assertRaises(ValueError):
                        OllamaLLM("model", **kwargs)


if __name__ == "__main__":
    unittest.main()
