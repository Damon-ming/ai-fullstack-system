# app-server/src/com/damon/ming/ai/inference/__init__.py
"""
推理服务抽象层 —— 纯技术模块，支持多种推理引擎。

提供：
  - BaseInferenceService: 推理服务抽象基类
  - StreamToken: 流式输出 token
  - InferenceParams: 纯数据类，参数由上层配置注入
  - register_engine: 引擎注册装饰器
  - resolve_engine: 根据引擎名称解析实现类
  - list_engines: 列出所有已注册的引擎名称

配置加载见 config/inference/，本模块不感知配置来源。

引擎注册表由各实现类通过 @register_engine 自动注册。
"""
from src.com.damon.ming.ai.inference.base_inference import (
    BaseInferenceService,
    InferenceParams,
    ModelOptions,
    StreamToken,
    list_engines,
    register_engine,
    resolve_engine,
)
from src.com.damon.ming.ai.inference.ollama_inference import OllamaInference
from src.com.damon.ming.ai.inference.vllm_inference import VLLMInference

__all__ = [
    "BaseInferenceService",
    "InferenceParams",
    "ModelOptions",
    "StreamToken",
    "OllamaInference",
    "VLLMInference",
    "register_engine",
    "resolve_engine",
    "list_engines",
]
