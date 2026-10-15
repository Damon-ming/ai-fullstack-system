# app-server/src/com/damon/ming/ai/registry/inference_registry.py
from src.com.damon.ming.ai.inference.factory import InferenceFactory
from src.com.damon.ming.ai.inference.ollama_inference import OllamaInference
from src.com.damon.ming.log import pin

logger = pin("InferenceRegistry")


def register_all_inferences():
    InferenceFactory.register("ollama", OllamaInference)
    # InferenceFactory.register("vllm", VLLMInference)
    logger.info(f"已注册推理后端: {InferenceFactory.list_providers()}")
