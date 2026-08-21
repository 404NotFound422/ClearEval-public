# custom_llm.py

from langchain_core.language_models.llms import LLM
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import logging
from typing import Optional
from pydantic import Field, BaseModel

logger = logging.getLogger(__name__)

class LocalLLM(LLM):
    model_path: str = Field(..., description="Path to the model")
    tokenizer_path: str = Field(..., description="Path to the tokenizer")
    device: str = Field(default="cuda", description="Device to run the model on")
    max_length: int = Field(default=500, description="Maximum length of generated text")
     
    tokenizer: Optional[AutoTokenizer] = None  
    model: Optional[AutoModelForCausalLM] = None

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, 
                 model_path: str, 
                 tokenizer_path: str, 
                 device: str = 'cuda', 
                 max_length: int = 500):
                
        model_kwargs = {
            "model_path": model_path,
            "tokenizer_path": tokenizer_path,
            "device": device,
            "max_length": max_length
        }
        
        super().__init__(**model_kwargs)  

        self.tokenizer = AutoTokenizer.from_pretrained(self.tokenizer_path, local_files_only=True)
        self.model = AutoModelForCausalLM.from_pretrained(self.model_path, local_files_only=True)
        if device =='cuda' and torch.cuda.is_available():
            print("GPU available, using CUDA.")
            self._device = torch.device(device)
        else:
            print("No GPU available, using CPU.")
            self._device = torch.device("cpu")

        self.model.to(self._device)
        self.max_length = max_length
        logger.info(f"Initialized LocalModel with model at {model_path} and tokenizer at {tokenizer_path}")
    
    def _call(self, prompt: str, stop: list = None) -> str:
        # 使用辅助方法 generate_with_params 处理生成逻辑
        return self.generate_with_params(prompt, max_length=self.max_length)
    def generate_with_params(self, prompt: str, max_length: int = 500) -> str:
        if max_length is None:
            max_length = self.max_length
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        outputs = self.model.generate(**inputs, max_length=max_length)
        response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        logger.debug(f"Generated response: {response}")
        return response
    
    @property
    def _llm_type(self) -> str:
        return "local_llm"
    