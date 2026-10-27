# 推理引擎配置加载器 -- 双源合并。
#
# 配置分为两层：
#   1. 连接配置：config/templates/{engine}.yaml（base_url / api_key / timeout / engine）
#      -> 模板即生产配置，引擎选择由 INFERENCE_SERVER 环境变量决定
#   2. 模型参数：inference-params.yaml（temperature / top_p / max_tokens）
#      -> AI 模块内部，与后端无关，任何推理服务通用
#
# 合并逻辑：
#   engine 类型取自 INFERENCE_SERVER 环境变量 -> config/templates/{engine}.yaml
#   base_url、timeout、api_key、model 取自连接配置模板
#   temperature、top_p、max_tokens 取自 inference-params.yaml
#
# 用法：
#   loader = InferenceConfigLoader()
#   result = loader.load_all()
#   engine, entry = loader.get_engine_for_model("chat")
#


import os
from dataclasses import dataclass
from typing import Any

import yaml
from src.com.damon.ming.ai.inference import resolve_engine
from src.com.damon.ming.ai.inference.base_inference import (
    BaseInferenceService,
    InferenceParams,
)

# ── 连接模板目录（app-server/config/templates/）──────────────────────────
# 模板即生产配置，按引擎名选取：config/templates/ollama.yaml / vllm.yaml
_TEMPLATES_DIR = os.path.normpath(
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "..",
        "..",
        "..",
        "..",
        "..",
        "..",
        "config",
        "templates",
    )
)

# ── 模型参数（AI 模块内，与后端无关）──────────────────────────────────
_PARAMS_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "inference-params.yaml")
)

# ── 环境变量覆盖模式 ───────────────────────────────────────────────────
# CHAT_TEMPERATURE=0.5  -> 覆盖 chat 角色的 temperature
# 格式：{ROLE_UPPER}_{PARAM}


@dataclass(frozen=True)
class ModelEntry:
    """模型层加载结果。"""

    model_name: str
    options: dict[str, Any]
    api_key: str
    engine_type: str


def _apply_env_overrides(role: str, options: dict[str, Any]) -> dict[str, Any]:
    """应用环境变量覆盖（格式：{ROLE_UPPER}_{PARAM}）。"""
    result = dict(options)
    role_upper = role.upper()
    for param in ("temperature", "top_p", "max_tokens"):
        env_key = f"{role_upper}_{param.upper()}"
        env_val = os.environ.get(env_key)
        if env_val is not None:
            # 尝试保持原类型
            original_type = type(options[param])
            try:
                result[param] = original_type(env_val)
            except (ValueError, TypeError):
                result[param] = env_val
    return result


class InferenceConfigLoader:
    """双源合并：config/templates/{engine}.yaml（连接） + inference-params.yaml（模型参数）。"""

    def __init__(self):
        self._engine_type: str = ""
        self._engines: dict[str, BaseInferenceService] = {}
        self._models: dict[str, ModelEntry] = {}

    def load_all(self) -> dict:
        """一次性加载引擎和模型配置，合并两个 YAML 源。"""
        # ── 确定引擎类型和连接模板路径 ──
        self._engine_type = os.environ.get("INFERENCE_SERVER", "ollama")
        conn_path = os.path.join(_TEMPLATES_DIR, f"{self._engine_type}.yaml")

        if not os.path.exists(conn_path):
            raise FileNotFoundError(
                f"连接模板不存在: {conn_path}（INFERENCE_SERVER={self._engine_type}）"
            )

        # ── 读取连接配置 ──
        with open(conn_path, "r", encoding="utf-8") as f:
            conn_cfg = yaml.safe_load(f)

        if not conn_cfg or "roles" not in conn_cfg:
            raise ValueError(f"连接模板格式错误，缺少 roles: {conn_path}")

        # ── 读取模型参数 ──
        if not os.path.exists(_PARAMS_PATH):
            raise FileNotFoundError(f"模型参数配置不存在: {_PARAMS_PATH}")

        with open(_PARAMS_PATH, "r", encoding="utf-8") as f:
            params_cfg = yaml.safe_load(f)

        if not params_cfg or "roles" not in params_cfg:
            raise ValueError(f"模型参数配置格式错误，缺少 roles: {_PARAMS_PATH}")

        params_roles = params_cfg["roles"]

        # ── 解析引擎类型 ──
        # 优先取 YAML 中的 engine 字段，其次用 INFERENCE_SERVER 环境变量
        engine_type = conn_cfg.get("engine") or self._engine_type
        self._engine_type = engine_type
        base_url = conn_cfg.get("base_url", "")
        timeout = conn_cfg.get("default_timeout", 180)
        impl_cls = resolve_engine(engine_type)

        # ── 逐角色合并 ──
        for role, role_conn in conn_cfg["roles"].items():
            if role not in params_roles:
                raise ValueError(
                    f"连接模板中的角色 '{role}' 在 inference-params.yaml 中缺少对应参数"
                )

            api_key = role_conn.get("api_key", "")
            model_name = role_conn.get("model", "")

            # api_key 为空时（如 Ollama），共享引擎
            engine_key = api_key or "__shared__"
            if engine_key not in self._engines:
                params = InferenceParams(
                    base_url=base_url,
                    timeout=timeout,
                    api_key=api_key,
                )
                self._engines[engine_key] = impl_cls(params)

            # 模型参数来自 inference-params.yaml + 环境变量覆盖
            raw_options = {k: v for k, v in params_roles[role].items()}
            options = _apply_env_overrides(role, raw_options)

            self._models[role] = ModelEntry(
                model_name=model_name,
                options=options,
                api_key=api_key,
                engine_type=engine_type,
            )

        return {
            "engines": self._engines,
            "models": self._models,
        }

    def get_engine_for_model(
        self, role: str = "chat"
    ) -> tuple[BaseInferenceService, ModelEntry]:
        """获取引擎实例和指定角色的模型信息。"""
        if not self._models:
            self.load_all()
        entry = self._models[role]
        engine_key = entry.api_key or "__shared__"
        engine = self._engines[engine_key]
        return engine, entry
