# app-server/src/com/damon/ming/encryption/encryption_config_loader.py
"""
加密体系配置加载器 —— 从 YAML 文件读取加密参数。

加载优先级：
  1. 显式传入的 config_path
  2. ENCRYPTION_CONFIG_PATH 环境变量
  3. 默认路径：本目录下的 encryption-config.yaml

支持多剖面（default / production），通过 profile 参数选择。
"""

import os

import yaml


class EncryptionConfig:
    """加密配置数据类。"""

    def __init__(self, raw: dict):
        self.rsa_key_size: int = int(raw.get("rsa_key_size", 2048))
        self.session_ttl_hours: int = int(raw.get("session_ttl_hours", 24))
        self.kek_salt: str = str(raw.get("kek_salt", "ming-ai-key-store-v1"))
        self.signature_tolerance_minutes: int = int(
            raw.get("signature_tolerance_minutes", 5)
        )
        self.signature_secret: str = str(raw.get("signature_secret", ""))

    @property
    def session_ttl_seconds(self) -> int:
        return self.session_ttl_hours * 3600


class EncryptionConfigLoader:
    """从 YAML 文件加载加密配置。

    用法：
        cfg = EncryptionConfigLoader().load()                    # 默认剖面
        cfg = EncryptionConfigLoader().load(profile="production") # 生产剖面
    """

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            config_path = os.environ.get("ENCRYPTION_CONFIG_PATH", "")
        if not config_path:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "encryption-config.yaml")
        self._config_path = config_path

    def load(self, profile: str = "default") -> EncryptionConfig:
        """加载指定剖面的配置。"""
        raw = self._read_yaml(profile)
        return EncryptionConfig(raw)

    def _read_yaml(self, profile: str) -> dict:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"加密配置文件不存在: {self._config_path}")
        with open(self._config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)
        if raw_cfg is None or "encryption" not in raw_cfg:
            raise ValueError("加密配置文件格式错误：缺少 'encryption' 根节点")
        section = raw_cfg["encryption"].get(profile, {})
        if not section:
            raise ValueError(f"加密配置文件中未找到剖面: {profile}")
        return section
