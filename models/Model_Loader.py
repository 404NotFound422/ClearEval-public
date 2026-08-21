# model_loader.py

import yaml
#from models.Custom_LLM import LocalLLM
from models.Ollama_LLM import OllamaLLM
from models.OpenAI_Model import OpenAILLM
from models.Huggingface_LLM import HuggingfaceLLM
from models.Gemini_Model import GeminiLLM
from models.GLM_Model import GLM
import logging

logger = logging.getLogger(__name__)

class ModelLoader:
    def __init__(self, config_path: str):
        with open(config_path, 'r',encoding='utf-8') as file:
            self.config = yaml.safe_load(file)
        logger.info(f"Loaded configuration from {config_path}")
    
    def load_models(self) -> dict:
        '''
        return: 
            模型实例, 可直接通过models[name]._call调用
            {'name': 'llama', 'instance': LocalLLM(...)} 
            OR
            {'name': 'openai_gpt-4', 'instance': OpenAI(...)}
        '''
        models = {}
        for model_conf in self.config.get('models', []):
            name = model_conf['name']
            #print("model_conf:", model_conf)
            
            if model_conf['type'] == 'Ollama':
                '''
                models[name] = LocalLLM(
                    model_path=model_conf['model_path'],
                    tokenizer_path=model_conf['tokenizer_path']
                )             
                '''
                models[name] = OllamaLLM(
                    model_name=model_conf['model_name'],
                    temperature=model_conf['temperature']
                )
                
            if model_conf['type'] == 'Huggingface':
                models[name] = HuggingfaceLLM(
                    model_name=model_conf['model_name'],
                    api_token=model_conf['api_token'],
                    temperature=model_conf['temperature']
                )

            elif model_conf['type'] == 'api':
                # Pass max_tokens if specified in config (critical for teacher model long outputs)
                max_tokens = model_conf.get('max_tokens', None)
                if 'openai' in model_conf['name'].lower():
                    kwargs = {
                        "model_name": model_conf['model_name'],
                        "api_key": model_conf['api_key'],
                        "base_url": model_conf['base_url'],
                        "temperature": model_conf.get('temperature', 0.7),
                        "enable_thinking": model_conf.get('enable_thinking', False),
                    }
                    if max_tokens is not None:
                        kwargs["max_tokens"] = max_tokens
                    models[name] = OpenAILLM(**kwargs)
                elif 'gemini' in model_conf['name'].lower():
                    kwargs = {
                        "model_name": model_conf['model_name'],
                        "api_key": model_conf['api_key'],
                        "base_url": model_conf['base_url'],
                        "temperature": model_conf['temperature'],
                    }
                    if max_tokens is not None:
                        kwargs["max_tokens"] = max_tokens
                    models[name] = GeminiLLM(**kwargs)
                elif 'glm' in model_conf['name'].lower():
                    kwargs = {
                        "model_name": model_conf['model_name'],
                        "api_key": model_conf['api_key'],
                        "base_url": model_conf['base_url'],
                        "temperature": model_conf.get('temperature', 0.1),
                        "enable_thinking": model_conf.get('enable_thinking', False),
                    }
                    if max_tokens is not None:
                        kwargs["max_tokens"] = max_tokens
                    models[name] = GLM(**kwargs)
                else:
                    raise ValueError(f"Unsupported API type for model: {name}")
            else:
                raise ValueError(f"Unsupported model type: {model_conf['type']}")
        return models
