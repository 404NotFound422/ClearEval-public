# openai_llm.py

from langchain_core.language_models.llms import LLM
from openai import AsyncOpenAI, OpenAI
import logging
import time
from typing import Optional, List
from pydantic import Field
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

logger = logging.getLogger(__name__)

class OpenAIOutputError(ValueError):
    """Technical output failure with safe provider metadata and partial text."""
    def __init__(self, reason, response_data):
        super().__init__("OpenAI-compatible output failed: " + reason)
        self.response_data = response_data


class OpenAITransportError(RuntimeError):
    def __init__(self, exception_type, response_data):
        # Never copy SDK exception text: it can contain endpoint or credential data.
        super().__init__("OpenAI-compatible transport failed: " + exception_type)
        self.response_data = response_data


class _CompletionState:
    def __init__(self, model_name):
        self.started = time.monotonic()
        self.content = ""
        self.finish_reason = None
        self.metadata = {"provider": "openai-compatible", "model": model_name}
        self.tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def result(self, failed=False):
        metadata = dict(self.metadata, finish_reason=self.finish_reason,
                        technical_status="FAILED" if failed else "VALID")
        result = {"content": "" if failed else self.content,
                  "time_cost": time.monotonic() - self.started,
                  "tokens_used": dict(self.tokens), "metadata": metadata}
        if failed:
            result["raw_content"] = self.content
        return result

    def fail(self, reason):
        raise OpenAIOutputError(reason, self.result(failed=True))

    def observe(self, response, streaming):
        for field in ("id", "model", "created", "system_fingerprint"):
            value = getattr(response, field, None)
            if isinstance(value, (str, int, float)):
                self.metadata[field] = value
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.tokens = {key: getattr(usage, key, None) for key in self.tokens}
        choices = getattr(response, "choices", None)
        if not choices:
            if not streaming:
                self.fail("missing_choices")
            return  # Streaming usage trailers contain no choices.
        if len(choices) != 1 or getattr(choices[0], "index", 0) != 0:
            self.fail("unexpected_choices")
        choice = choices[0]
        reason = getattr(choice, "finish_reason", None)
        text = getattr(choice.delta if streaming else choice.message, "content", None)
        if self.finish_reason is not None:
            self.fail("choice_after_terminal_event")
        if text is not None:
            if not isinstance(text, str):
                self.fail("invalid_content")
            self.content += text
        if reason is not None:
            self.finish_reason = reason
            if reason != "stop":
                self.fail("unusable_finish_reason")

    def complete(self):
        if self.finish_reason != "stop":
            self.fail("missing_finish_reason")
        if not self.content.strip():
            self.fail("empty_content")
        return self.result()


class OpenAILLM(LLM):
    model_name: str = Field(..., description="Name of the OpenAI model to use")
    api_key: str = Field(..., description="OpenAI API key")
    base_url: str = Field(default="https://api.openai.com/v1", description="OpenAI API base URL")
    temperature: float = Field(default=0.1, description="Sampling temperature")
    max_tokens: int = Field(default=50000, description="Maximum number of tokens to generate")
    top_p: float = Field(default=1.0, description="Top p sampling parameter")
    frequency_penalty: float = Field(default=0.0, description="Frequency penalty parameter")
    presence_penalty: float = Field(default=0.0, description="Presence penalty parameter")
    
    client: Optional[AsyncOpenAI] = None
    enable_thinking: bool = Field(default=False, description="Enable thinking mode for qwen models")
    def __init__(self, 
                 model_name: str, 
                 api_key: str, 
                 base_url: str = "https://api.openai.com/v1",
                 temperature: float = 0.7,
                 max_tokens: int = 5000,
                 top_p: float = 1.0,
                 frequency_penalty: float = 0.0,
                 presence_penalty: float = 0.0,
                 enable_thinking: bool = False
                 ):
        
        model_kwargs = {
            "model_name": model_name,
            "api_key": api_key,
            "base_url": base_url,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
            "enable_thinking": enable_thinking
        }
        
        super().__init__(**model_kwargs)

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            http_client=httpx.AsyncClient(trust_env=False)
        )
        
        logger.info(f"Initialized OpenAILLM with model {model_name}")

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> dict:
        return self.generate_with_params(
            prompt,
            max_length=self.max_tokens,
            temperature=self.temperature,
            stop=stop
        )

    def _request_params(self, prompt, max_length=None, temperature=None, top_p=None,
                        frequency_penalty=None, presence_penalty=None, stop=None):
        maximum = self.max_tokens if max_length is None else max_length
        params = {
            "model": self.model_name, "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature if temperature is None else temperature,
            "top_p": self.top_p if top_p is None else top_p,
            "frequency_penalty": self.frequency_penalty if frequency_penalty is None else frequency_penalty,
            "presence_penalty": self.presence_penalty if presence_penalty is None else presence_penalty,
            "stop": stop,
        }
        if "o4" in self.model_name.lower() or "5.2" in self.model_name.lower():
            params["extra_body"] = {"max_completion_tokens": maximum}
        else:
            params["max_tokens"] = maximum
        if "qwen" in self.model_name.lower():
            params.update(stream=True, stream_options={"include_usage": True})
            params.setdefault("extra_body", {})["enable_thinking"] = self.enable_thinking
        return params

    def generate_with_params(self, prompt, max_length=None, temperature=None, top_p=None,
                             frequency_penalty=None, presence_penalty=None, stop=None):
        """Use a synchronous SDK client; never call AsyncOpenAI without awaiting."""
        params = self._request_params(prompt, max_length, temperature, top_p,
                                      frequency_penalty, presence_penalty, stop)
        state = _CompletionState(self.model_name)
        try:
            with OpenAI(api_key=self.api_key, base_url=self.base_url,
                        http_client=httpx.Client(trust_env=False)) as client:
                response = client.chat.completions.create(**params)
                if params.get("stream"):
                    try:
                        for chunk in response:
                            state.observe(chunk, streaming=True)
                    finally:
                        response.close()
                else:
                    state.observe(response, streaming=False)
        except OpenAIOutputError:
            raise
        except Exception as exc:
            raise OpenAITransportError(type(exc).__name__, state.result(failed=True)) from None
        return state.complete()

    @property
    def _llm_type(self) -> str:
        return "openai_llm"

    async def _acall(self, prompt: str, stop: Optional[List[str]] = None) -> dict:
        return await self.generate_with_params_async(
            prompt,
            max_length=self.max_tokens,
            temperature=self.temperature,
            stop=stop
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(OpenAITransportError),
        reraise=True,
    )
    async def generate_with_params_async(self, prompt, max_length=None, temperature=None, top_p=None,
                                     frequency_penalty=None, presence_penalty=None, stop=None):
        params = self._request_params(prompt, max_length, temperature, top_p,
                                      frequency_penalty, presence_penalty, stop)
        state = _CompletionState(self.model_name)
        try:
            response = await self.client.chat.completions.create(**params)
            if params.get("stream"):
                try:
                    async for chunk in response:
                        state.observe(chunk, streaming=True)
                finally:
                    await response.close()
            else:
                state.observe(response, streaming=False)
        except OpenAIOutputError:
            raise
        except Exception as exc:
            raise OpenAITransportError(type(exc).__name__, state.result(failed=True)) from None
        return state.complete()

    async def aclose(self):
        await self.client.close()

    def get_num_tokens(self, text: str) -> int:
        """
        Get the number of tokens in a text string.
        This is a simple estimation method.
        """
        return len(text.split())