"""Run the actual adapter module with SDK doubles; no installed SDK/network needed."""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

N = types.SimpleNamespace


def module(name, **attrs):
    value = types.ModuleType(name)
    value.__dict__.update(attrs)
    return value


class FakeLLM:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class Stream:
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False
    def __iter__(self):
        return iter(self.chunks)
    def __aiter__(self):
        self.iterator = iter(self.chunks)
        return self
    async def __anext__(self):
        try:
            return next(self.iterator)
        except StopIteration:
            raise StopAsyncIteration
    async def close(self):
        self.closed = True


class SyncStream(Stream):
    def close(self):
        self.closed = True


class AsyncSDK:
    response = None
    exception = None
    instances = []
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        self.closed = False
        self.chat = N(completions=N(create=self.create))
        self.instances.append(self)
    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exception:
            raise self.exception
        return self.response
    async def close(self):
        self.closed = True


class SyncSDK(AsyncSDK):
    instances = []
    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.exception:
            raise self.exception
        return self.response
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.closed = True


def load_adapter():
    doubles = {
        "langchain_core": module("langchain_core"),
        "langchain_core.language_models": module("langchain_core.language_models"),
        "langchain_core.language_models.llms": module("llms", LLM=FakeLLM),
        "openai": module("openai", AsyncOpenAI=AsyncSDK, OpenAI=SyncSDK,
                         APIError=RuntimeError, Timeout=TimeoutError),
        "pydantic": module("pydantic", Field=lambda default=None, **kw: default, BaseModel=object),
        "tenacity": module("tenacity", retry=lambda **kw: lambda fn: fn,
                           stop_after_attempt=lambda *a: None, wait_exponential=lambda **kw: None,
                           retry_if_exception_type=lambda *a: None),
        "httpx": module("httpx", Client=lambda **kw: N(**kw), AsyncClient=lambda **kw: N(**kw)),
    }
    spec = importlib.util.spec_from_file_location("openai_adapter_under_test",
        Path(__file__).resolve().parents[1] / "models/OpenAI_Model.py")
    adapter = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, doubles):
        spec.loader.exec_module(adapter)
    return adapter


def completion(text="complete protocol", reason="stop"):
    return N(id="synthetic-request", model="synthetic-model", created=1,
             choices=[N(index=0, message=N(content=text), finish_reason=reason)],
             usage=N(prompt_tokens=2, completion_tokens=3, total_tokens=5))


def chunk(text=None, reason=None, usage=None):
    return N(choices=[N(index=0, delta=N(content=text), finish_reason=reason)], usage=usage)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.adapter = load_adapter()
        for sdk in (AsyncSDK, SyncSDK):
            sdk.response = None
            sdk.exception = None
            sdk.instances.clear()
        self.model = self.adapter.OpenAILLM("synthetic-model", "synthetic-key")

    def async_call(self):
        return asyncio.run(self.model._acall("synthetic prompt"))

    def test_async_stop_preserves_provider_metadata_and_usage(self):
        AsyncSDK.response = completion()
        result = self.async_call()
        self.assertEqual(result["content"], "complete protocol")
        self.assertEqual(result["metadata"]["finish_reason"], "stop")
        self.assertEqual(result["metadata"]["id"], "synthetic-request")
        self.assertEqual(result["metadata"]["technical_status"], "VALID")
        self.assertEqual(result["tokens_used"]["total_tokens"], 5)

    def test_async_bad_terminal_reason_never_returns_partial_content(self):
        for reason in ("length", "content_filter", "tool_calls", None):
            with self.subTest(reason=reason):
                AsyncSDK.response = completion("partial text", reason)
                with self.assertRaises(self.adapter.OpenAIOutputError) as caught:
                    self.async_call()
                response = caught.exception.response_data
                self.assertEqual(response["content"], "")
                self.assertEqual(response["raw_content"], "partial text")
                self.assertEqual(response["metadata"]["technical_status"], "FAILED")
                self.assertEqual(response["metadata"]["finish_reason"], reason)

    def test_empty_text_and_missing_choices_fail(self):
        for response in (completion(""), completion("  "), completion(None), N(choices=[], usage=None)):
            AsyncSDK.response = response
            with self.assertRaises(self.adapter.OpenAIOutputError):
                self.async_call()

    def test_qwen_stream_requires_stop_and_preserves_usage_trailer(self):
        self.model.model_name = "qwen-synthetic"
        stream = Stream([chunk("complete "), chunk("protocol", "stop"),
                         N(choices=[], usage=N(prompt_tokens=2, completion_tokens=3, total_tokens=5))])
        AsyncSDK.response = stream
        result = self.async_call()
        self.assertEqual(result["content"], "complete protocol")
        self.assertEqual(result["tokens_used"]["total_tokens"], 5)
        self.assertTrue(stream.closed)
        self.assertTrue(self.model.client.calls[0]["stream"])

    def test_qwen_stream_truncation_filter_missing_terminal_empty_are_failures(self):
        self.model.model_name = "qwen-synthetic"
        for chunks in ([chunk("partial", "length")], [chunk("partial", "content_filter")],
                       [chunk("partial")], [chunk(None, "stop")]):
            AsyncSDK.response = Stream(chunks)
            with self.assertRaises(self.adapter.OpenAIOutputError):
                self.async_call()
            self.assertTrue(AsyncSDK.response.closed)

    def test_stream_choice_after_terminal_event_fails(self):
        self.model.model_name = "qwen-synthetic"
        AsyncSDK.response = Stream([chunk("complete", "stop"), chunk("extra")])
        with self.assertRaises(self.adapter.OpenAIOutputError):
            self.async_call()

    def test_sync_uses_sync_sdk_and_closes_client(self):
        SyncSDK.response = completion()
        result = self.model._call("synthetic prompt")
        self.assertEqual(result["content"], "complete protocol")
        self.assertTrue(SyncSDK.instances[-1].closed)
        self.assertEqual(self.model.client.calls, [])

    def test_sync_stream_success_and_close(self):
        self.model.model_name = "qwen-synthetic"
        SyncSDK.response = SyncStream([chunk("complete", "stop")])
        result = self.model._call("synthetic prompt")
        self.assertEqual(result["content"], "complete")
        self.assertEqual(result["metadata"]["finish_reason"], "stop")
        self.assertTrue(SyncSDK.response.closed)

    def test_sync_nonstream_and_stream_terminal_failures(self):
        for model, response in (("synthetic", completion("partial", "length")),
                                ("qwen-synthetic", SyncStream([chunk("partial")])),
                                ("qwen-synthetic", SyncStream([chunk("partial", "content_filter")]))):
            self.model.model_name = model
            SyncSDK.response = response
            with self.assertRaises(self.adapter.OpenAIOutputError):
                self.model._call("synthetic prompt")
            self.assertTrue(SyncSDK.instances[-1].closed)

    def test_transport_errors_propagate_without_secret_exception_text(self):
        for sdk, call in ((AsyncSDK, self.async_call), (SyncSDK, lambda: self.model._call("prompt"))):
            sdk.exception = RuntimeError("SYNTHETIC_PRIVATE_SENTINEL")
            with self.assertRaises(self.adapter.OpenAITransportError) as caught:
                call()
            self.assertNotIn("SYNTHETIC_PRIVATE_SENTINEL", str(caught.exception))
            self.assertEqual(caught.exception.response_data["content"], "")

    def test_explicit_zero_temperature_is_sent(self):
        AsyncSDK.response = completion()
        asyncio.run(self.model.generate_with_params_async("prompt", temperature=0))
        self.assertEqual(self.model.client.calls[-1]["temperature"], 0)


if __name__ == "__main__":
    unittest.main()
