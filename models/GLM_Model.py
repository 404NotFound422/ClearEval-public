# models/GLM_Model.py

from langchain_core.language_models.llms import LLM
from openai import AsyncOpenAI, APIError, Timeout
import logging
import time
import asyncio
from typing import Optional, List, Dict, Any
from pydantic import Field
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

logger = logging.getLogger(__name__)

class GLM(LLM):
    """
    智谱清言 GLM 模型集成类。
    支持 GLM-4/GLM-5 系列模型，并提供“思考模式”(Thinking Mode) 的支持。
    
    注意：为了与本代码库的 TOCBenchmark 兼容，_call 和 _acall 返回 Dict 类型，
    这虽然偏离了标准 LangChain LLM 接口（应返回 str），但符合本项目现有的架构约定。
    """
    model_name: str = Field(..., description="模型名称，例如 'glm-4-plus' 或 'glm-5'")
    api_key: str = Field(..., description="智谱 AI API Key")
    base_url: str = Field(default="https://open.bigmodel.cn/api/paas/v4", description="API 基础 URL")
    temperature: float = Field(default=0.1, description="采样温度")
    max_tokens: int = Field(default=4096, description="最大生成 token 数")
    enable_thinking: bool = Field(default=False, description="是否开启思考模式")
    
    client: Optional[AsyncOpenAI] = None

    def __init__(self, 
                 model_name: str, 
                 api_key: str, 
                 base_url: str = "https://open.bigmodel.cn/api/paas/v4",
                 temperature: float = 0.1,
                 max_tokens: int = 4096,
                 enable_thinking: bool = False,
                 **kwargs):
        """
        初始化 GLM 模型。
        """
        model_kwargs = {
            "model_name": model_name,
            "api_key": api_key,
            "base_url": base_url,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "enable_thinking": enable_thinking,
            **kwargs
        }
        
        super().__init__(**model_kwargs)

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            http_client=httpx.AsyncClient(trust_env=False)
        )
        
        logger.info(f"Initialized GLM model {model_name} with enable_thinking={enable_thinking}")

    def _call(self, prompt: str, stop: Optional[List[str]] = None, **kwargs) -> Dict[str, Any]:
        """
        同步调用方法。注意：本项目主要使用异步接口 _acall。
        """
        try:
            return asyncio.run(self._acall(prompt, stop, **kwargs))
        except RuntimeError:
            # 如果已经在运行的 loop 中，这种调用在没有 nest_asyncio 的情况下会失败
            # 但在本项目的核心评测流程中（test.py），使用的是 _acall
            raise RuntimeError("GLM._call 只能在没有运行中的 event loop 的线程中调用。请在异步环境中使用 _acall。")

    async def _acall(self, prompt: str, stop: Optional[List[str]] = None, **kwargs) -> Dict[str, Any]:
        """
        异步调用方法。
        
        Returns:
            Dict: 包含 content, time_cost, tokens_used 的字典。
        """
        return await self.generate_with_params_async(
            prompt,
            max_length=self.max_tokens,
            temperature=self.temperature,
            stop=stop,
            **kwargs
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=(retry_if_exception_type(Timeout) | retry_if_exception_type(APIError))
    )
    async def generate_with_params_async(self, prompt: str, max_length: int = None, temperature: float = None, 
                                     stop: Optional[List[str]] = None, **kwargs) -> Dict[str, Any]:
        """
        执行异步生成任务。
        """
        start_time = time.time()
        
        max_length = max_length or self.max_tokens
        temperature = temperature or self.temperature

        messages = [{"role": "user", "content": prompt}]

        # 配置思考模式
        extra_body = {
            "thinking": {
                "type": "enabled" if self.enable_thinking else "disabled"
            }
        }

        response_data = {
            "content": "",
            "reasoning_content": "",
            "time_cost": 0,
            "tokens_used": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }

        try:
            if not kwargs.get("stream", False):
                response = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_length,
                    stop=stop,
                    extra_body=extra_body
                )
                
                message = response.choices[0].message
                content = message.content or ""
                reasoning_content = getattr(message, "reasoning_content", "") or ""
                # 当 thinking 模式开启且 content 为空时，使用 reasoning_content 作为回退
                if not content and reasoning_content:
                    content = reasoning_content
                response_data["content"] = content
                response_data["reasoning_content"] = reasoning_content
                
                if response.usage:
                    response_data["tokens_used"] = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    }
            else:
                response = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_length,
                    stop=stop,
                    stream=True,
                    extra_body=extra_body
                )
                
                full_content = ""
                full_reasoning = ""
                async for chunk in response:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, "content") and delta.content:
                        full_content += delta.content
                    if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                        full_reasoning += delta.reasoning_content
                    
                    if chunk.usage:
                        response_data["tokens_used"] = {
                            "prompt_tokens": chunk.usage.prompt_tokens,
                            "completion_tokens": chunk.usage.completion_tokens,
                            "total_tokens": chunk.usage.total_tokens
                        }
                
                # 当 thinking 模式开启且 content 为空时，使用 reasoning_content 作为回退
                if not full_content and full_reasoning:
                    full_content = full_reasoning
                response_data["content"] = full_content
                response_data["reasoning_content"] = full_reasoning

        except Exception as e:
            logger.error(f"Error calling GLM API: {e}")
            response_data["content"] = f"Error: {e}"

        end_time = time.time()
        response_data["time_cost"] = end_time - start_time
        return response_data

    @property
    def _llm_type(self) -> str:
        return "glm"
