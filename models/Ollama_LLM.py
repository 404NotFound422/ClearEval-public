# ollama_llm.py

from langchain_core.language_models.llms import LLM
import logging
from typing import Optional, List
from pydantic import Field, BaseModel

# 条件导入 ollama
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    # 创建一个模拟的 ollama 客户端类
    class MockOllamaClient:
        def generate(self, model, prompt, options=None):
            return {"response": f"模拟响应 (模型: {model})"}
    
    class ollama:
        @staticmethod
        def Client():
            return MockOllamaClient()

logger = logging.getLogger(__name__)
# 尝试导入ollama，如果不可用则创建虚拟类
try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logger.warning("Ollama module not found. Using mock implementation.")
    
    # 创建虚拟的Ollama Client类
    class MockOllamaClient:
        def generate(self, model: str, prompt: str, options: dict[str, any] = None) -> dict[str, any]:
            logger.warning(f"Using mock Ollama client with model {model}. This will not produce real results.")
            return {
                "response": f"[Mock Response] This is a simulated response for prompt: {prompt[:30]}...",
                "model": model,
                "created_at": "2023-01-01T00:00:00Z",
                "done": True
            }
    
    # 创建虚拟的ollama模块
    class MockOllama:
        @staticmethod
        def Client() -> MockOllamaClient:
            return MockOllamaClient()
    
    # 替换ollama模块
    ollama = MockOllama()


class OllamaLLM(LLM):
    model_name: str = Field(..., description="Name of the Ollama model to use")
    max_length: int = Field(default=500, description="Maximum length of generated text")
    temperature: float = Field(default=0.1, description="Sampling temperature")
    
    client: Optional[object] = None

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, 
                 model_name: str,
                 max_length: int = 500,
                 temperature: float = 0.1):
                
        model_kwargs = {
            "model_name": model_name,
            "max_length": max_length,
            "temperature": temperature
        }
        
        super().__init__(**model_kwargs)  

        self.client = ollama.Client()
        if not OLLAMA_AVAILABLE:
            logger.warning("Ollama 包未安装，使用模拟客户端")
        else:
            logger.info(f"Initialized OllamaLLM with model {model_name}")
    
    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        # 使用辅助方法 generate_with_params 处理生成逻辑
        return self.generate_with_params(prompt, max_length=self.max_length)

    def generate_with_params(self, 
                           prompt: str, 
                           max_length: Optional[int] = None,
                           temperature: Optional[float] = None) -> str:
        """
        Generate text with specific parameters
        """
        if max_length is None:
            max_length = self.max_length
        if temperature is None:
            temperature = self.temperature

        try:
            response = self.client.generate(
                model=self.model_name,
                prompt=prompt,
                options={
                    "num_tokens": max_length,
                    "temperature": temperature
                }
            )
            result = response.get('response', '')
            logger.debug(f"Generated response: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            if not OLLAMA_AVAILABLE:
                return f"模拟响应 (由于 Ollama 未安装): 提示词长度 {len(prompt)} 字符"
            raise
    
    @property
    def _llm_type(self) -> str:
        return "ollama_llm"