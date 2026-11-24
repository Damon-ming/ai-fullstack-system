"""共享模型配置的公开接口。"""

from ._catalog import ModelConfig, ModelConfigError, get_model_config

__all__ = ["ModelConfig", "ModelConfigError", "get_model_config"]
