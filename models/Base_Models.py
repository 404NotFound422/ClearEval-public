'''
V20241223_LLMServer_ModelsLayer_Base_Models_test_00
模型层抽象函数, 用于执行模型生成命令。
'''

from abc import ABC, abstractmethod

class BaseModel(ABC):
    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        pass