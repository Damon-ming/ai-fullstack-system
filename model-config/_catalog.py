"""配置存储和校验实现；调用方只使用包的公开接口。"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import yaml


class ModelConfigError(ValueError):
    """模型不存在或配置无效。"""


@dataclass(frozen=True)
class ModelConfig:
    name: str
    model_type: str
    max_model_len: int
    dimension: int | None = None
    max_input_tokens: int | None = None


def _read_model_values(path: Path) -> dict:
    try:
        models = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ModelConfigError(f"模型配置读取失败: {exc}") from exc
    if not isinstance(models, dict):
        raise ModelConfigError("模型配置必须是 YAML 映射")
    names = set()
    for group in ("inference", "embedding"):
        entries = models.get(group)
        if not isinstance(entries, dict) or not entries:
            raise ModelConfigError(f"模型配置缺少有效的 {group} 分组")
        for name, entry in entries.items():
            if not isinstance(name, str) or not name.strip() or not isinstance(entry, dict):
                raise ModelConfigError(f"{group} 的模型名称和参数格式无效")
            if name in names:
                raise ModelConfigError(f"模型 {name!r} 出现在多个分组，模型 key 必须唯一")
            window = entry.get("max-model-len")
            if type(window) is not int or window <= 0:
                raise ModelConfigError(f"{name}.max-model-len 必须是正整数")
            dimension = entry.get("dimension")
            if group == "embedding" or dimension is not None:
                if type(dimension) is not int or dimension <= 0:
                    raise ModelConfigError(f"{name}.dimension 必须是正整数")
            max_input_tokens = entry.get("max-input-tokens")
            if group == "embedding" or max_input_tokens is not None:
                if type(max_input_tokens) is not int or max_input_tokens <= 0:
                    raise ModelConfigError(
                        f"{name}.max-input-tokens 必须是正整数"
                    )
                if max_input_tokens > window:
                    raise ModelConfigError(
                        f"{name}.max-input-tokens 不能大于 max-model-len"
                    )
            names.add(name)
    return models


def _read_catalog(path: Path) -> Mapping[str, ModelConfig]:
    models = _read_model_values(path)
    return MappingProxyType({
        name: ModelConfig(
            name=name,
            model_type=group,
            max_model_len=entry["max-model-len"],
            dimension=entry.get("dimension"),
            max_input_tokens=entry.get("max-input-tokens"),
        )
        for group in ("inference", "embedding")
        for name, entry in models[group].items()
    })


@lru_cache(maxsize=1)
def _get_catalog() -> Mapping[str, ModelConfig]:
    return _read_catalog(Path(__file__).with_name("models.yaml"))


def get_model_config(model_name: str) -> ModelConfig:
    """按完整模型名获取只读配置；不需要调用方指定文件或模型分组。"""
    if not isinstance(model_name, str) or not model_name.strip():
        raise ModelConfigError("模型名必须是非空字符串")
    entry = _get_catalog().get(model_name)
    if entry is None:
        raise ModelConfigError(f"找不到模型 {model_name!r}")
    return entry
