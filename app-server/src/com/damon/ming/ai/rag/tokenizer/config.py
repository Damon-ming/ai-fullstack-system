"""分词器的 YAML 配置映射与校验。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# todo: 为什么需要这么多config
@dataclass(frozen=True, kw_only=True)
class TokenizerRoleConfig:
    tokenizer_engine: str
    params: dict[str, Any]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.tokenizer_engine, str)
            or not self.tokenizer_engine.strip()
        ):
            raise ValueError("配置缺少有效的 tokenizer_engine 字段")
        if not isinstance(self.params, dict):
            raise TypeError("分词器 params 必须是键值对象")
        if self.tokenizer_engine == "tiktoken":
            encoding_name = self.params.get("encoding_name")
            if not isinstance(encoding_name, str) or not encoding_name.strip():
                raise ValueError("分词器缺少有效的 params.encoding_name")
        elif self.tokenizer_engine == "jieba":
            dicts_dir = self.params.get("dicts_dir")
            if dicts_dir is not None and not isinstance(dicts_dir, str):
                raise TypeError("分词器 params.dicts_dir 必须是字符串")
        else:
            raise ValueError(
                f"分词器引擎 '{self.tokenizer_engine}' 尚未配置对应的参数解析器"
            )


@dataclass(frozen=True, kw_only=True)
class TokenizerConfig:
    roles: dict[str, TokenizerRoleConfig]

    def __post_init__(self) -> None:
        if not isinstance(self.roles, dict) or not self.roles:
            raise ValueError("RAG tokenizer 配置缺少 roles")
        if not all(
            isinstance(role, TokenizerRoleConfig) for role in self.roles.values()
        ):
            raise TypeError("RAG tokenizer roles 必须使用 TokenizerRoleConfig")

    @classmethod
    def from_mapping(cls, raw: Any) -> TokenizerConfig:
        if not isinstance(raw, dict):
            raise TypeError("RAG tokenizer 配置必须是键值对象")
        raw_roles = raw.get("roles")
        if not isinstance(raw_roles, dict) or not raw_roles:
            raise ValueError("RAG tokenizer 配置缺少 roles")
        roles: dict[str, TokenizerRoleConfig] = {}
        for name, entry in raw_roles.items():
            if not isinstance(entry, dict):
                raise TypeError(f"分词器配置 '{name}' 必须是键值对象")
            try:
                roles[name] = TokenizerRoleConfig(
                    tokenizer_engine=entry.get("tokenizer_engine"),
                    params=entry.get("params", {}),
                )
            except (TypeError, ValueError) as exc:
                raise type(exc)(f"分词器配置 '{name}' 无效: {exc}") from exc
        return cls(roles=roles)
