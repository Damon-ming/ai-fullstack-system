"""加载 RAG embedding 的文本前缀参数。"""

from pathlib import Path

from src.com.damon.ming.utils.yaml_loader import load_yaml, resolve_yaml_path


class EmbeddingBusinessConfigLoader:
    def __init__(self, config_path: str | None = None) -> None:
        directory = config_path or str(Path(__file__).resolve().parent)
        self._config_path = resolve_yaml_path(directory)

    def load(self) -> dict:
        raw = load_yaml(self._config_path)
        if not isinstance(raw, dict):
            raise TypeError("RAG embedding 配置必须是 YAML 对象")
        common = raw.get("common")
        if not isinstance(common, dict):
            raise TypeError("RAG embedding 配置缺少 common")
        return dict(common)
