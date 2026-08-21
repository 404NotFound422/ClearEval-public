# huggingface_llm.py

from langchain_core.language_models.llms import LLM
from langchain_huggingface import HuggingFaceEndpoint
import logging
from typing import Optional, List
from pydantic import Field, BaseModel

logger = logging.getLogger(__name__)

class HuggingfaceLLM(LLM):
    model_name: str = Field(..., description="Name of the HuggingFace model to use")
    api_token: str = Field(..., description="HuggingFace API token")
    max_length: int = Field(default=500, description="Maximum length of generated text")
    temperature: float = Field(default=0.1, description="Sampling temperature")
    
    client: Optional[HuggingFaceEndpoint] = None

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, 
                 model_name: str,
                 api_token: str,
                 max_length: int = 500,
                 temperature: float = 0.1):
                
        model_kwargs = {
            "model_name": model_name,
            "api_token": api_token,
            "max_length": max_length,
            "temperature": temperature
        }
        
        super().__init__(**model_kwargs)  

        self.client = HuggingFaceEndpoint(
            repo_id=self.model_name,
            temperature=self.temperature,
            max_new_tokens=self.max_length,
            huggingfacehub_api_token=self.api_token
        )
        logger.info(f"Initialized HuggingFaceLLM with model {model_name}")
    
    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        # 使用辅助方法 generate_with_params 处理生成逻辑
        return self.generate_with_params(prompt, max_length=self.max_length, temperature=self.temperature)

    def generate_with_params(self, 
                           prompt: str, 
                           max_length: Optional[int] = None,
                           temperature: Optional[float] = None) -> str:
        """
        Generate text with specific parameters
        """
        try:
            # 使用 HuggingFace endpoint 生成响应
            response = self.client.invoke(prompt)
            logger.debug(f"Generated response: {response}")
            return response
            
        except Exception as e:
            logger.error(f"Error generating response while using Huggingface: {str(e)}")
            raise
    
    @property
    def _llm_type(self) -> str:
        return "huggingface_llm"