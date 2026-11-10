# app-server/src/com/damon/ming/app/config/encryption/encryption_config_loader.py
"""
加密体系配置加载器 —— 从 YAML 文件读取加密业务参数。

本模块属于 app/ 业务层，不属于 encryption/ 模块。
encryption/ 模块通过 setter 接收参数，不感知配置来源。

配置来源：本目录下唯一的 YAML 文件（支持多剖面 debug / release，由 profile 参数选择，默认跟随运行时环境）。
"""

import os

from src.com.damon.ming.app.config._yaml import load_yaml
from src.com.damon.ming.debug import get_env


class EncryptionConfig:
    """加密配置数据类（所有字段必填，无默认值）。"""

    KEYS = (
        "rsa_key_size",
        "session_ttl_hours",
        "sign_context",
        "kek_salt",
        "kek_info",
        "data_key_id",
    )

    def __init__(self, raw: dict):
        missing = [k for k in self.KEYS if raw.get(k) is None]
        if missing:
            raise ValueError(f"加密配置缺少必填字段：{', '.join(missing)}")

        self.rsa_key_size: int = int(raw["rsa_key_size"])
        self.session_ttl_hours: int = int(raw["session_ttl_hours"])
        self.sign_context: str = str(raw["sign_context"])
        self.kek_salt: str = str(raw["kek_salt"])
        self.kek_info: str = str(raw["kek_info"])
        self.data_key_id: str = str(raw["data_key_id"])

    @property
    def session_ttl_seconds(self) -> int:
        return self.session_ttl_hours * 3600


class EncryptionConfigLoader:
    """从 YAML 文件加载加密配置。

    用法：
        cfg = EncryptionConfigLoader().load()                    # 跟随运行时环境
        cfg = EncryptionConfigLoader().load(profile="release")   # 指定剖面
    """

    def __init__(self):
        self._config_dir = os.path.dirname(os.path.abspath(__file__))

    def load(self, profile: str | None = None) -> EncryptionConfig:
        """加载指定剖面的配置。必填字段缺失直接抛异常，不做静默降级。

        Args:
            profile: 剖面名（debug / release）。默认为当前运行时环境。
        """
        if profile is None:
            profile = get_env()
        raw = self._read_yaml(profile)
        try:
            return EncryptionConfig(raw)
        except ValueError as e:
            raise ValueError(f"{e} | profile={profile}") from e

    def _read_yaml(self, profile: str) -> dict:
        raw_cfg = load_yaml(self._config_dir)
        if "encryption" not in raw_cfg:
            raise ValueError("加密配置文件格式错误：缺少 'encryption' 根节点")
        section = raw_cfg["encryption"].get(profile, {})
        if not section:
            raise ValueError(f"加密配置文件中未找到剖面: {profile}")
        return section
