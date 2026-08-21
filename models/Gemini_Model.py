# gemini_model.py

import asyncio
from langchain_core.language_models.llms import LLM
import google.generativeai as genai 
import logging
from typing import Optional, List
from pydantic import Field
import inspect

logger = logging.getLogger(__name__)

class GeminiLLM(LLM):
    model_name: str = Field(..., description="Name of the Gemini model to use, e.g., 'gemini-1.5-flash'")
    api_key: str = Field(..., description="Gemini API key")
    api_endpoint: str = Field(..., description="Gemini API endpoint ")
    temperature: float = Field(default=0.7, description="Sampling temperature")
    max_tokens: int = Field(default=2048, description="Maximum number of tokens to generate")

    client: Optional[genai.GenerativeModel] = None

    class Config:
        arbitrary_types_allowed = True # To allow genai.GenerativeModel type

    def __init__(self,
                 model_name: str,
                 api_key: str,
                 base_url: str,
                 temperature: float = 0.7,
                 max_tokens: int = 30000
                 ):
        model_kwargs = {
            "model_name": model_name,
            "api_key": api_key,
            "api_endpoint": base_url,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        super().__init__(**model_kwargs)

        # Configure the genai library globally.
        # Note: This is a global setting for the google.generativeai module.
        # If using multiple instances with different API keys/endpoints in the same process,
        # ensure this is managed appropriately or consider advanced configuration.
        genai.configure(
            api_key=self.api_key,
            transport="rest", # As per user's requirement
            client_options={"api_endpoint": self.api_endpoint} # As per user's requirement
        )

        # Set default generation configuration for the model instance
        default_generation_config = genai.types.GenerationConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_tokens
        )

        # Initialize the generative model client
        self.client = genai.GenerativeModel(
            model_name=self.model_name,
            generation_config=default_generation_config
        )
        logger.info(f"Initialized GeminiLLM with model {self.model_name}, endpoint {self.api_endpoint}")

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        """
        Makes a call to the Gemini model.
        """
        return self.generate_with_params(
            prompt,
            max_tokens=self.max_tokens, # Uses instance default
            temperature=self.temperature, # Uses instance default
            stop=stop
        )

    def generate_with_params(self,
                           prompt: str,
                           max_tokens: Optional[int] = None,
                           temperature: Optional[float] = None,
                           stop: Optional[List[str]] = None) -> str:
        """
        Generate text with specific parameters, overriding instance defaults if provided.
        """
        # Determine effective parameters, using instance defaults if not overridden
        current_max_tokens = max_tokens if max_tokens is not None else self.max_tokens
        current_temperature = temperature if temperature is not None else self.temperature

        # Prepare generation_config dictionary
        generation_config_params = {}
        if current_temperature is not None:
            generation_config_params["temperature"] = current_temperature
        if current_max_tokens is not None:
            generation_config_params["max_output_tokens"] = current_max_tokens
        if stop:
            generation_config_params["stop_sequences"] = stop
        
        # Create a GenerationConfig object if there are specific parameters to apply
        config_to_use = None
        if generation_config_params:
            config_to_use = genai.types.GenerationConfig(**generation_config_params)

        try:
            # Make the API call
            response = self.client.generate_content(
                prompt,
                generation_config=config_to_use # Pass None to use client's default config
            )

            # Process the response
            if response.parts:
                result = "".join(part.text for part in response.parts if hasattr(part, 'text'))
            elif hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
                # Handle cases where content generation is blocked
                block_reason_message = getattr(response.prompt_feedback, 'block_reason_message', 'Unknown reason')
                logger.error(f"Content generation blocked by Gemini. Reason: {response.prompt_feedback.block_reason}. Message: {block_reason_message}")
                raise Exception(f"Content generation blocked by Gemini: {block_reason_message}")
            else:
                # Handle cases with no parts and no explicit block reason (e.g., empty response)
                logger.warning("Gemini response has no parts and no explicit block reason. Returning empty string.")
                result = ""

            logger.debug(f"Generated response: {result}")
            return result

        except Exception as e:
            logger.error(f"Error generating response from Gemini: {str(e)}")
            # Re-raise the exception to be handled by the caller
            raise

    @property
    def _llm_type(self) -> str:
        """Return type of llm."""
        return "gemini_llm"

    async def _acall(self, prompt: str, stop: Optional[List[str]] = None) -> dict:
        return await self.generate_with_params_async(
            prompt,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stop=stop
        )

    async def generate_with_params_async(self,
                                       prompt: str,
                                       max_tokens: Optional[int] = None,
                                       temperature: Optional[float] = None,
                                       stop: Optional[List[str]] = None) -> dict:
        import time
        start_time = time.time()

        current_max_tokens = max_tokens if max_tokens is not None else self.max_tokens
        current_temperature = temperature if temperature is not None else self.temperature

        generation_config_params = {}
        if current_temperature is not None:
            generation_config_params["temperature"] = current_temperature
        if current_max_tokens is not None:
            generation_config_params["max_output_tokens"] = current_max_tokens
        if stop:
            generation_config_params["stop_sequences"] = stop

        config_to_use = None
        if generation_config_params:
            config_to_use = genai.types.GenerationConfig(**generation_config_params)

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
            # 正确异步调用
            # Fallback to sync call in thread because generate_content_async appears broken in this version
            # (throws "object GenerateContentResponse can't be used in 'await' expression" when awaited)
            def run_sync():
                return self.client.generate_content(
                prompt,
                generation_config=config_to_use
            )

            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, run_sync)

            if response.parts:
                response_data["content"] = "".join(part.text for part in response.parts if hasattr(part, 'text'))
            elif hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
                block_reason_message = getattr(response.prompt_feedback, 'block_reason_message', 'Unknown reason')
                logger.error(f"Content generation blocked by Gemini. Reason: {response.prompt_feedback.block_reason}. Message: {block_reason_message}")
                response_data["content"] = f"Error: Content generation blocked - {block_reason_message}"
            else:
                logger.warning("Gemini response has no parts and no explicit block reason. Returning empty string.")
                response_data["content"] = ""

        except Exception as e:
            logger.error(f"Error generating response from Gemini: {str(e)}")
            response_data["content"] = f"Error: {e}"

        end_time = time.time()
        response_data["time_cost"] = end_time - start_time
        # Gemini API does not return token usage in the same way as OpenAI.
        # We can estimate it or leave it as 0.
        # For now, leaving as 0.
        return response_data

    def get_num_tokens(self, text: str) -> int:
        """
        Get the number of tokens in a text string.
        This is a simple estimation method using word count.
        For accurate Gemini token counts, a model-specific tokenizer would be needed.
        """
        return len(text.split())

if __name__ == '__main__':
    
    try:
        logger.basicConfig(level=logging.INFO)

        # llm = GeminiLLM(
        #     model_name=gemini_model_name,
        #     api_key=gemini_api_key,
        #     api_endpoint=gemini_api_endpoint,
        #     temperature=0.5
        # )
        # response_text = llm._call("Say Hello to the Gemini world!")
        # print(f"Gemini Response: {response_text}")

        # To run the exact example from the prompt:
        genai.configure(
            api_key='', # Replace with your key
            transport="rest",
            client_options={"api_endpoint": ""} # Replace with your endpoint
        )
        model = genai.GenerativeModel('gemini-2.5-flash') # Replace with your model
        response = model.generate_content("Say Hello")
        print(f"Direct SDK Response: {response.text}")
        
    except Exception as e:
        print(f"An error occurred during the example usage: {e}")