"""读取模型规格并集中提供 App 侧 AI 运行预算。"""

import os
import re

# 当前运行预算与模型配置速查（移除每行开头的 # 后是有效 JSON）：
# {
#   "model_config_source": "model-config/models.yaml -> model-config.env -> Compose 注入 app-server",
#   "roles": {
#     "inference": {
#       "model_name": "qwen2.5-1.8B-instruct",
#       "max-model-len": 4096,
#       "max_output_tokens": 2048
#     },
#     "summary": {
#       "model_name": "qwen2.5-0.5B-instruct",
#       "max-model-len": 2048,
#       "max_output_tokens": 1024,
#     },
#     "guardrail": {
#       "model_name": "qwen3guard-gen-0.6b",
#       "max-model-len": 4096,
#       "max_output_tokens": 128
#     }
#   },
#   "embedding": {
#     "role": "bge_m3",
#     "model_name": "BAAI/bge-m3",
#     "max-model-len": 8192,
#     "max-input-tokens": 8182,
#     "dimension": 1024,
#   },
#   "rag_context_max_tokens": 1024,
#   "rag_max_chunk_token_size": 768
# }
# inference-config.yaml 和 embedding-config.yaml 中的 model_name 决定读取哪个模型规格；
# 修改模型规格后，请同步更新此速查 JSON。

# RAG 返回给主推理模型的参考上下文 token 上限。
# rag_core.py 用它限制检索结果；超限摘要也以此作为目标输出长度。
RAG_CONTEXT_MAX_TOKENS = 1024

# RAG 文档切分的目标 chunk 大小；启动时会按 embedding 模型输入上限收紧。
RAG_MAX_CHUNK_TOKEN_SIZE = 768

# 按业务 role 配置默认输出上限；各次请求仍可通过调用参数降低上限。
# summary 默认跟随 RAG_CONTEXT_MAX_TOKENS；当前 RAG 摘要调用会显式传入该值。
DEFAULT_MAX_OUTPUT_TOKENS_BY_ROLE = {
    "inference": 2048,
    "summary": RAG_CONTEXT_MAX_TOKENS,
    "guardrail": 128,
}


def get_default_max_output_tokens(role: str) -> int:
    """按业务 role 返回默认输出 token 上限。"""
    try:
        return DEFAULT_MAX_OUTPUT_TOKENS_BY_ROLE[role]
    except KeyError as exc:
        raise ValueError(f"没有为推理 role '{role}' 配置默认 max_tokens") from exc


def _get_model_int(model_name: str, field: str) -> int:
    """按模型名和 model-config 字段读取对应的整型环境变量。"""
    if not isinstance(model_name, str) or not model_name.strip():
        raise ValueError("model_name 必须是非空字符串")

    model_id = model_name.rsplit("/", 1)[-1]
    prefix = re.sub(r"[^A-Za-z0-9]+", "_", model_id).strip("_").upper()
    if not prefix or prefix[0].isdigit():
        raise ValueError(f"无法从模型名生成环境变量前缀: {model_name!r}")

    field_suffix = re.sub(r"[^A-Za-z0-9]+", "_", field).strip("_").upper()
    variable = f"{prefix}_{field_suffix}"
    value = os.environ.get(variable)
    if value is None or not value.strip():
        raise ValueError(
            f"模型 '{model_name}' 缺少环境变量 {variable}；"
            "请确认根目录 model-config.env 已生成并注入 app-server"
        )
    try:
        value_int = int(value)
    except ValueError as exc:
        raise ValueError(f"环境变量 {variable} 必须是整数") from exc
    if value_int < 1:
        raise ValueError(f"环境变量 {variable} 必须是正整数")
    if field == "max-model-len" and value_int < 2:
        raise ValueError(f"环境变量 {variable} 必须是大于等于 2 的整数")
    return value_int


def get_model_max_len(model_name: str) -> int:
    """读取模型部署窗口（MAX_MODEL_LEN）。"""
    return _get_model_int(model_name, "max-model-len")


def get_model_max_input_tokens(model_name: str) -> int:
    """读取 embedding 模型的可用输入 token 上限。"""
    return _get_model_int(model_name, "max-input-tokens")


def get_model_dimension(model_name: str) -> int:
    """读取 embedding 模型输出向量维度。"""
    return _get_model_int(model_name, "dimension")
