# app-server/src/com/damon/ming/ai/inference/__init__.py
"""推理服务接口与引擎注册入口，目前仅提供 vLLM 实现。"""

from src.com.damon.ming.ai.inference.base_inference import (
    BaseInferenceService,
    InferenceParams,
    ModelOptions,
    StreamToken,
    list_engines,
    register_engine,
    resolve_engine,
)
from src.com.damon.ming.ai.inference.config import InferenceConfig
from src.com.damon.ming.ai.inference.inference_gateway import InferenceGateway
from src.com.damon.ming.ai.inference.params import InferenceRoleParams
from src.com.damon.ming.ai.inference.vllm_inference import VLLMInference

__all__ = [
    "BaseInferenceService",
    "InferenceConfig",
    "InferenceGateway",
    "InferenceParams",
    "InferenceRoleParams",
    "ModelOptions",
    "StreamToken",
    "VLLMInference",
    "list_engines",
    "register_engine",
    "resolve_engine",
]
