"""
models.yaml 加载器 —— 集中化模型行为配置。

职责：
  - 加载 ai/config/models.yaml
  - 应用环境变量覆盖
  - 返回 {role: options} 映射

调用方（推理服务）通过构造函数传入加载结果，本模块不持有服务引用。
"""

import os
from typing import Any

import yaml

_MODELS_YAML_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "models.yaml")
)


class ModelsConfigLoader:
    """加载 models.yaml 并应用环境变量覆盖。"""

    def load(self) -> dict[str, dict[str, Any]]:
        """返回 {role: options} 映射。

        优先级：环境变量 > models.yaml。
        models.yaml 缺失或格式错误直接报错，无硬编码兜底。
        """
        if not os.path.exists(_MODELS_YAML_PATH):
            raise FileNotFoundError(f"models.yaml 不存在: {_MODELS_YAML_PATH}")

        with open(_MODELS_YAML_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or "roles" not in data:
            raise ValueError(f"models.yaml 缺少 'roles' 块: {_MODELS_YAML_PATH}")

        return {
            role: self._apply_env_overrides(role, defaults)
            for role, defaults in data["roles"].items()
        }

    @staticmethod
    def _apply_env_overrides(role: str, defaults: dict[str, Any]) -> dict[str, Any]:
        """用环境变量覆盖 models.yaml 中的参数。返回新 dict，不修改入参。"""
        result = dict(defaults)
        role_upper = role.upper()

        for key, val in defaults.items():
            env_key = f"{role_upper}_{key.upper()}"
            env_val = os.environ.get(env_key)
            if env_val is not None:
                result[key] = float(env_val) if isinstance(val, float) else int(env_val)

        return result
