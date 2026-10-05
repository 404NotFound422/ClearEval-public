"""Load only selected provider adapters; configuration reads never create clients."""
import importlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def read_model_config(config_path):
    """Accept stdlib JSON or optional PyYAML, without logging secret values."""
    path = Path(config_path)
    with path.open("r", encoding="utf-8-sig") as handle:
        if path.suffix.lower() == ".json":
            from evaluator_integrity import parse_judge_object
            value = parse_judge_object(handle.read())
        else:
            try:
                import yaml
            except ImportError as exc:
                raise ImportError("YAML model configuration requires PyYAML; JSON needs no YAML dependency.") from exc
            value = yaml.safe_load(handle)
    if not isinstance(value, dict) or not isinstance(value.get("models"), list):
        raise ValueError("Model configuration must contain a models list.")
    normalized = []
    names = set()
    for index, entry in enumerate(value["models"]):
        if not isinstance(entry, dict):
            raise ValueError("Model configuration entry %d must be an object." % index)
        row = dict(entry)
        for field in ("name", "type", "model_name"):
            item = row.get(field)
            if not isinstance(item, str) or not item.strip():
                raise ValueError("Model configuration entry %d requires nonempty %s." % (index, field))
            row[field] = item.strip()
        if row["name"] in names:
            raise ValueError("Model configuration has duplicate names after whitespace normalization.")
        names.add(row["name"])
        normalized.append(row)
    return dict(value, models=normalized)


class ModelLoader:
    def __init__(self, config_path):
        self.config = read_model_config(config_path)
        from evaluation_contract import sha256_file
        self.configuration_file_sha256 = sha256_file(config_path)
        logger.info("Loaded model configuration.")

    def load_models(self, model_names=None):
        """Omit model_names for legacy all-model loading; select names for normal OEQ."""
        selected = None if model_names is None else set(model_names)
        available = {row["name"] for row in self.config["models"]}
        if selected is not None and not selected.issubset(available):
            raise ValueError("Requested model names are absent from the configuration.")
        models = {}
        for row in self.config["models"]:
            name = row["name"]
            if selected is not None and name not in selected:
                continue
            kind = row["type"].casefold()
            if kind == "ollama":
                cls = importlib.import_module("models.Ollama_LLM").OllamaLLM
                kwargs = {
                    "model_name": row["model_name"],
                    "temperature": row.get("temperature", 0.1),
                    "max_length": row.get("max_tokens", row.get("max_length", 8192)),
                    "timeout": row.get("timeout", 300),
                }
                for key in ("host", "format", "enable_thinking", "transport", "num_ctx", "seed"):
                    if key in row:
                        kwargs[key] = row[key]
                models[name] = cls(**kwargs)
            elif kind == "huggingface":
                cls = importlib.import_module("models.Huggingface_LLM").HuggingfaceLLM
                models[name] = cls(
                    model_name=row["model_name"], api_token=row["api_token"],
                    temperature=row.get("temperature", 0.1),
                )
            elif kind == "api":
                maximum = row.get("max_tokens")
                kwargs = {
                    "model_name": row["model_name"], "api_key": row["api_key"],
                    "base_url": row["base_url"].strip(),
                    "temperature": row.get("temperature", 0.7),
                }
                if maximum is not None:
                    kwargs["max_tokens"] = maximum
                if "openai" in name.lower():
                    cls = importlib.import_module("models.OpenAI_Model").OpenAILLM
                    kwargs["enable_thinking"] = row.get("enable_thinking", False)
                elif "gemini" in name.lower():
                    cls = importlib.import_module("models.Gemini_Model").GeminiLLM
                elif "glm" in name.lower():
                    cls = importlib.import_module("models.GLM_Model").GLM
                    kwargs["temperature"] = row.get("temperature", 0.1)
                    kwargs["enable_thinking"] = row.get("enable_thinking", False)
                else:
                    raise ValueError("Unsupported API provider; model name must identify openai, gemini, or glm.")
                models[name] = cls(**kwargs)
            else:
                raise ValueError("Unsupported model type; supported types: Ollama, Huggingface, api.")
            # Private fingerprints bind configuration without publishing keys or endpoints.
            from evaluation_contract import json_hash
            try:
                object.__setattr__(models[name], "_configuration_sha256", json_hash(row))
                object.__setattr__(models[name], "_configuration_file_sha256", self.configuration_file_sha256)
            except (AttributeError, TypeError):
                pass  # Test doubles can be mappings; real provider adapters are objects.
        return models
