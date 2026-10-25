# app-server/src/com/damon/ming/ai/inference/inference_service.py
"""
LiteLLM 适配层 —— 配置分离：

  ① 后端选择（ollama / vllm）→ INFERENCE_SERVER 环境变量（部署时确定）
  ② 后端连接（model + api_base）→ ai/config/backends/<backend>.yaml（静态）
  ③ 业务参数（temperature / top_p / max_tokens / timeout）→ ai/config/models.yaml（集中化）
  ④ 部署覆盖 → 环境变量 {ROLE}_{PARAM}（最高优先级）

切换后端：改 INFERENCE_SERVER 一个变量，compose 自动起对应容器，代码自动加载对应 YAML。
加新后端：新建 <backend>.yaml + docker-<backend>.yaml，零代码改动。
改模型参数：改 models.yaml 或设置环境变量覆盖。
"""

import asyncio
import os
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import litellm
import yaml
from src.com.damon.ming.ai.inference.base_inference import (
    BaseInferenceService,
    InferenceParams,
)
from src.com.damon.ming.log import pin

logger = pin("InferenceService")


@dataclass(frozen=True)
class ModelConfig:
    """单个角色的推理配置（后端 YAML 提供 model/api_base，options 由上层注入）。"""

    model_name: str
    litellm_model: str
    api_base: str
    options: dict[str, Any] = field(default_factory=dict)


class LiteLLMInferenceService(BaseInferenceService):
    """LiteLLM 封装 —— 后端 YAML 提供 model/api_base，业务参数由构造函数传入。

    继承 BaseInferenceService 以获得统一的 classify_intention / rewrite_query 实现。
    """

    def __init__(self, roles_cfg: dict[str, dict[str, Any]]):
        # BaseInferenceService 要求 InferenceParams，此处用占位值
        # （LiteLLM 多角色共享实例，无单一 base_url）
        super().__init__(InferenceParams(base_url="", timeout=0, api_key=""))
        self._models: dict[str, ModelConfig] = {}
        self._backend: str = ""
        self._roles_cfg = roles_cfg

    def load(self) -> "LiteLLMInferenceService":
        """加载配置：后端 YAML 提供 model/api_base，roles_cfg 提供业务参数。"""
        # 1. 后端选择
        self._backend = os.environ.get("INFERENCE_SERVER") or "ollama"

        # 2. 加载后端 YAML（model + api_base）
        backend_cfg = self._load_backend_yaml(self._backend)

        # 3. 每个角色合并配置
        for role, options in self._roles_cfg.items():
            if role not in backend_cfg:
                raise ValueError(
                    f"后端 '{self._backend}' 的 YAML 缺少角色 '{role}' 配置"
                )

            backend_role = backend_cfg[role]
            litellm_model = backend_role.get("model", "")
            api_base = backend_role.get("api_base", "")

            if not litellm_model or not api_base:
                raise ValueError(
                    f"后端 '{self._backend}' 角色 '{role}' 缺少 model 或 api_base"
                )

            self._models[role] = ModelConfig(
                model_name=role,
                litellm_model=litellm_model,
                api_base=api_base,
                options=options,
            )

            logger.info(
                "推理角色加载 | role=%s | model=%s | api_base=%s | options=%s",
                role,
                litellm_model,
                api_base,
                self._models[role].options,
            )

        logger.info(
            "LiteLLM 推理服务初始化完成 | backend=%s | 角色数: %d",
            self._backend,
            len(self._models),
        )
        return self

    def get_model(self, role: str) -> ModelConfig:
        """获取指定角色的模型配置。"""
        if role not in self._models:
            raise ValueError(
                f"未知推理角色: '{role}'。可用: {list(self._models.keys())}"
            )
        return self._models[role]

    def list_roles(self) -> list[str]:
        """列出所有已配置的角色。"""
        return list(self._models.keys())

    @property
    def backend(self) -> str:
        """当前使用的后端名称。"""
        return self._backend

    # ── 核心推理接口 ──────────────────────────────────────────────────

    async def text_generation(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        reason: bool = False,
        response_schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        """一次性返回完整文本。"""
        merged_opts = dict(options) if options else {}
        timeout = merged_opts.pop("timeout", 180)

        extra_kwargs: dict[str, Any] = {}
        if response_schema is not None:
            extra_kwargs["response_format"] = {
                "type": "json_object",
                "schema": response_schema,
            }

        try:
            resp = await litellm.acompletion(
                model=model_name,
                messages=messages,
                stream=False,
                timeout=timeout,
                **extra_kwargs,
                **merged_opts,
            )
            return resp.choices[0].message.content or ""
        except litellm.Timeout:
            raise TimeoutError(f"推理超时 | model={model_name} | timeout={timeout}s")
        except asyncio.CancelledError:
            logger.warning("text_generation 任务被取消")
            raise

    async def stream_generate(
        self,
        model_name: str,
        messages: list[dict[str, str]],
        reason: bool = False,
        response_schema: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> AsyncGenerator[StreamToken, None]:
        """流式 SSE 输出 —— 产出 StreamToken 区分 reasoning / content。"""
        merged_opts = dict(options) if options else {}
        timeout = merged_opts.pop("timeout", 180)

        extra_kwargs: dict[str, Any] = {"stream": True}
        if response_schema is not None:
            extra_kwargs["response_format"] = {
                "type": "json_object",
                "schema": response_schema,
            }

        try:
            resp = await litellm.acompletion(
                model=model_name,
                messages=messages,
                timeout=timeout,
                **extra_kwargs,
                **merged_opts,
            )
            async for chunk in resp:
                delta = chunk.choices[0].delta
                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    yield StreamToken(content=reasoning, type="reasoning")
                content = delta.content
                if content:
                    yield StreamToken(content=content, type="content")
        except litellm.Timeout:
            raise TimeoutError(f"流式推理超时 | model={model_name}")
        except asyncio.CancelledError:
            logger.warning("stream_generate 任务被取消")
            raise
        except Exception:
            logger.exception("流式推理失败 | model=%s", model_name)
            raise

    async def check_model_ready(self, role: str = "chat") -> bool:
        """检测指定角色的模型是否可用。"""
        try:
            model_cfg = self.get_model(role)
            resp = await litellm.acompletion(
                model=model_cfg.litellm_model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
                timeout=10,
            )
            return resp is not None
        except Exception as e:
            logger.warning("模型就绪检测失败 | role=%s | error=%s", role, e)
            return False

    def get_model_info(self, role: str = "chat") -> dict[str, Any]:
        """获取指定角色的模型信息（监控/日志用）。"""
        try:
            cfg = self.get_model(role)
            return {
                "role": role,
                "backend": self._backend,
                "litellm_model": cfg.litellm_model,
                "api_base": cfg.api_base,
                "options": cfg.options,
            }
        except ValueError:
            return {"role": role, "error": "not_configured"}

    # ── classify_intention / rewrite_query 继承自 BaseInferenceService ──

    # ── 私有 ─────────────────────────────────────────────────────────

    def _load_backend_yaml(self, backend: str) -> dict:
        """加载指定后端的 YAML 配置。"""
        config_dir = os.path.normpath(
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "config", "backends"
            )
        )
        yaml_path = os.path.join(config_dir, f"{backend}.yaml")

        if not os.path.exists(yaml_path):
            available = self._list_available_backends(config_dir)
            raise FileNotFoundError(
                f"后端配置文件不存在: {yaml_path}。可用后端: {available}"
            )

        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if data is None:
            raise ValueError(f"后端配置文件为空: {yaml_path}")
        return data

    def _list_available_backends(self, config_dir: str) -> list[str]:
        """列出可用后端。"""
        if not os.path.isdir(config_dir):
            return []
        return [
            os.path.splitext(f)[0]
            for f in os.listdir(config_dir)
            if f.endswith((".yaml", ".yml"))
        ]
