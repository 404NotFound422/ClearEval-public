"""Real local Ollama REST adapter with optional official SDK transport."""
import asyncio
import importlib
import math
import time
import json
import urllib.parse
import urllib.request


class OllamaOutputError(ValueError):
    """Retain failed provider output for the caller's failure audit."""
    def __init__(self, message, *, provider_response=None, finish_reason=None):
        super().__init__(message)
        self.provider_response = provider_response
        response = provider_response if isinstance(provider_response, dict) else {}
        self.finish_reason = finish_reason if finish_reason is not None else response.get("done_reason")
        self.response_data = None
        if provider_response is not None:
            metadata = {"provider": "ollama", "technical_status": "FAILED",
                        "done": response.get("done"), "done_reason": self.finish_reason,
                        "finish_reason": self.finish_reason,
                        "prompt_tokens": response.get("prompt_eval_count"),
                        "completion_tokens": response.get("eval_count"),
                        "provider_response": provider_response}
            self.response_data = {"content": "", "metadata": metadata}
            if isinstance(response.get("response"), str):
                self.response_data["raw_content"] = response["response"]


def _positive_integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("%s must be a positive integer." % label)
    return value


def _integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("%s must be an integer." % label)
    return value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LocalOllamaHTTPClient:
    """Real local REST transport; ignores environment proxies and refuses redirects."""
    def __init__(self, host="http://localhost:11434", timeout=300):
        parsed = urllib.parse.urlsplit(host)
        if (parsed.scheme not in ("http", "https") or parsed.hostname not in ("localhost", "127.0.0.1", "::1")
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ("", "/")):
            raise ValueError("The stdlib Ollama transport requires a local loopback origin URL.")
        self.endpoint = host.rstrip("/") + "/api/generate"
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def generate(self, **kwargs):
        payload = json.dumps(kwargs, ensure_ascii=False, allow_nan=False).encode("utf-8")
        request = urllib.request.Request(self.endpoint, data=payload,
                                         headers={"Content-Type": "application/json"}, method="POST")
        with self.opener.open(request, timeout=self.timeout) as response:
            raw = response.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise OllamaOutputError("Ollama response exceeded the 16 MiB transport limit.")
        from evaluator_integrity import parse_judge_object
        return parse_judge_object(raw.decode("utf-8"))

    def close(self):
        pass


class OllamaLLM:
    """_acall returns OEQ's content/metadata mapping; _call returns text."""
    def __init__(self, model_name, max_length=8192, temperature=0.1,
                 host=None, timeout=300, format=None, enable_thinking=False, transport="http",
                 num_ctx=None, seed=None):
        if not isinstance(model_name, str) or not model_name.strip():
            raise ValueError("Ollama model_name must be nonempty.")
        self.model_name = model_name.strip()
        self.max_length = _positive_integer(max_length, "max_length")
        self.temperature = self._temperature(temperature)
        self.num_ctx = None if num_ctx is None else _positive_integer(num_ctx, "num_ctx")
        self.seed = None if seed is None else _integer(seed, "seed")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Ollama timeout must be finite and positive.")
        self.timeout = timeout
        if format is not None and format != "json" and not isinstance(format, dict):
            raise ValueError("Ollama format must be json or a JSON schema object.")
        self.format = format
        if enable_thinking is not None and not isinstance(enable_thinking, bool):
            raise ValueError("enable_thinking must be a boolean when specified.")
        self.enable_thinking = enable_thinking
        if host is not None and (not isinstance(host, str) or not host.strip()):
            raise ValueError("Ollama host must be a nonempty URL.")
        self.host = host.strip() if host is not None else "http://localhost:11434"
        self.transport = transport
        if transport == "http":
            self.client = LocalOllamaHTTPClient(self.host, timeout)
        elif transport == "sdk":
            try:
                sdk = importlib.import_module("ollama")
            except ImportError as exc:
                raise ImportError("The official ollama Python package is required for SDK transport; no mock output is available.") from exc
            self.client = sdk.Client(host=self.host, timeout=timeout)
        else:
            raise ValueError("Ollama transport must be http or sdk.")

    @staticmethod
    def _temperature(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("temperature must be finite and nonnegative.")
        return value

    def _generate(self, prompt, max_length=None, temperature=None, stop=None, num_ctx=None, seed=None):
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Ollama prompt must be nonempty text.")
        maximum = self.max_length if max_length is None else _positive_integer(max_length, "max_length")
        temp = self.temperature if temperature is None else self._temperature(temperature)
        options = {"num_predict": maximum, "temperature": temp}
        context = self.num_ctx if num_ctx is None else _positive_integer(num_ctx, "num_ctx")
        random_seed = self.seed if seed is None else _integer(seed, "seed")
        if context is not None:
            options["num_ctx"] = context
        if random_seed is not None:
            options["seed"] = random_seed
        if stop is not None:
            if not isinstance(stop, list) or any(not isinstance(item, str) for item in stop):
                raise ValueError("stop must be a list of strings.")
            options["stop"] = stop
        kwargs = {"model": self.model_name, "prompt": prompt, "options": options, "stream": False}
        if self.format is not None:
            kwargs["format"] = self.format
        if self.enable_thinking is not None:
            kwargs["think"] = self.enable_thinking
        start = time.monotonic()
        response = self.client.generate(**kwargs)
        if hasattr(response, "model_dump"):
            response = response.model_dump()
        if not isinstance(response, dict):
            raise OllamaOutputError("Ollama returned an unsupported response structure.", provider_response=response)
        if response.get("done") is not True:
            raise OllamaOutputError("Ollama returned an incomplete response.", provider_response=response)
        reason = response.get("done_reason")
        if reason in ("length", "max_tokens", "limit"):
            raise OllamaOutputError("Ollama generation stopped at its token limit.", provider_response=response)
        count = response.get("eval_count")
        if not reason and isinstance(count, int) and count >= maximum:
            raise OllamaOutputError("Ollama token budget was exhausted without a verified stop reason.", provider_response=response)
        content = response.get("response")
        if not isinstance(content, str) or not content.strip():
            raise OllamaOutputError("Ollama returned empty generated text.", provider_response=response)
        if self.format is not None:
            from evaluator_integrity import parse_judge_object
            try:
                parse_judge_object(content)
            except ValueError as exc:
                raise OllamaOutputError("Ollama returned invalid formatted generated text: " + str(exc),
                                        provider_response=response) from exc
        metadata = {
            "provider": "ollama", "model": response.get("model", self.model_name),
            "done": True, "done_reason": reason,
            "prompt_tokens": response.get("prompt_eval_count"),
            "completion_tokens": count, "duration_seconds": time.monotonic() - start,
            "transport": self.transport, "provider_response": response,
        }
        return {"content": content, "metadata": metadata}

    def _call(self, prompt, stop=None, **kwargs):
        return self._generate(prompt, stop=stop, **kwargs)["content"]

    async def _acall(self, prompt, stop=None, **kwargs):
        return await asyncio.to_thread(self._generate, prompt, stop=stop, **kwargs)

    def generate_with_params(self, prompt, max_length=None, temperature=None, stop=None, num_ctx=None, seed=None):
        return self._generate(prompt, max_length, temperature, stop, num_ctx, seed)["content"]

    def invoke(self, prompt, **kwargs):
        return self._call(prompt, **kwargs)

    async def aclose(self):
        close = getattr(self.client, "close", None)
        if close:
            await asyncio.to_thread(close)

    @property
    def _llm_type(self):
        return "ollama_llm"
