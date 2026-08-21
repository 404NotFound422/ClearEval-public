# openai_llm.py

from langchain_core.language_models.llms import LLM
from openai import AsyncOpenAI, APIError, Timeout
import logging
import time
from typing import Optional, List
from pydantic import Field, BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

logger = logging.getLogger(__name__)

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

    def generate_with_params(self, prompt, max_length=None, temperature=None, top_p=None,
                             frequency_penalty=None, presence_penalty=None, stop=None):
        """
        使用指定参数生成文本，并返回耗时和tokens使用情况
        """
        start_time = time.time()
        flag_steam_completion = False  # Initialize flag_steam_completion

        # 使用传入的参数，如果没有则使用默认值
        max_length = max_length or self.max_tokens
        temperature = temperature or self.temperature
        top_p = top_p or self.top_p
        frequency_penalty = frequency_penalty or self.frequency_penalty
        presence_penalty = presence_penalty or self.presence_penalty

        # 构建消息
        messages = [{"role": "user", "content": prompt}]

        # 处理特殊参数
        extra_params = {}
        extra_body = {}
        if "qwen" in self.model_name.lower():
            flag_steam_completion = True
            extra_params["stream"] = True
            extra_params["stream_options"] = {"include_usage": True}
            extra_params["extra_body"] = {"enable_thinking": self.enable_thinking}

        if "o4" in self.model_name.lower() or "5.2" in self.model_name.lower():
            extra_body["max_completion_tokens"] = max_length
            #extra_params["max_completion_tokens"] = max_length
        else:
            extra_params["max_tokens"] = max_length

        if extra_body:
            extra_params["extra_body"] = extra_body

        response_data = {
            "content": "",
            "time_cost": 0,
            "tokens_used": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }

        try:
            if not flag_steam_completion:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=temperature,
                    stop=stop,
                    **extra_params
                )
                response_data["content"] = response.choices[0].message.content
                if response.usage:
                    response_data["tokens_used"] = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    }
            else:
                extra_params.pop('stream', None)
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=temperature,
                    stop=stop,
                    stream=True,
                    **extra_params
                )
                full_content = ""
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content is not None:
                        full_content += chunk.choices[0].delta.content
                    if chunk.usage:
                        response_data["tokens_used"] = {
                            "prompt_tokens": chunk.usage.prompt_tokens,
                            "completion_tokens": chunk.usage.completion_tokens,
                            "total_tokens": chunk.usage.total_tokens
                        }
                response_data["content"] = full_content

        except Exception as e:
            print(f"Error generating response: {e}")
            response_data["content"] = f"Error generating response: {e}"

        end_time = time.time()
        response_data["time_cost"] = end_time - start_time
        return response_data

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
        retry=(retry_if_exception_type(Timeout) | retry_if_exception_type(APIError))
    )
    async def generate_with_params_async(self, prompt, max_length=None, temperature=None, top_p=None,
                                     frequency_penalty=None, presence_penalty=None, stop=None):
        start_time = time.time()
        flag_steam_completion = False

        max_length = max_length or self.max_tokens
        temperature = temperature or self.temperature
        top_p = top_p or self.top_p
        frequency_penalty = frequency_penalty or self.frequency_penalty
        presence_penalty = presence_penalty or self.presence_penalty

        messages = [{"role": "user", "content": prompt}]

        extra_params = {}
        extra_body = {}
        if "qwen" in self.model_name.lower():
            flag_steam_completion = True
            extra_params["stream"] = True
            extra_params["stream_options"] = {"include_usage": True}
            extra_params["extra_body"] = {"enable_thinking": self.enable_thinking}

        if "o4" in self.model_name.lower() or "5.2" in self.model_name.lower():
            extra_body["max_completion_tokens"] = max_length
            #extra_params["max_completion_tokens"] = max_length
        else:
            extra_params["max_tokens"] = max_length

        if extra_body:
            extra_params["extra_body"] = extra_body

        response_data = {
            "content": "",
            "time_cost": 0,
            "tokens_used": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }

        try:
            if not flag_steam_completion:
                response = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=temperature,
                    stop=stop,
                    **extra_params
                )
                response_data["content"] = response.choices[0].message.content
                if response.usage:
                    response_data["tokens_used"] = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    }
            else:
                extra_params.pop('stream', None)
                response = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=temperature,
                    stop=stop,
                    stream=True,
                    **extra_params
                )
                full_content = ""
                async for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content is not None:
                        full_content += chunk.choices[0].delta.content
                    if chunk.usage:
                        response_data["tokens_used"] = {
                            "prompt_tokens": chunk.usage.prompt_tokens,
                            "completion_tokens": chunk.usage.completion_tokens,
                            "total_tokens": chunk.usage.total_tokens
                        }
                response_data["content"] = full_content

        except Exception as e:
            print(f"Error generating response: {e}")
            response_data["content"] = f"Error generating response: {e}"

        end_time = time.time()
        response_data["time_cost"] = end_time - start_time
        return response_data

    def get_num_tokens(self, text: str) -> int:
        """
        Get the number of tokens in a text string.
        This is a simple estimation method.
        """
        return len(text.split())