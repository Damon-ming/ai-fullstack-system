# app-server/src/com/damon/ming/app/config/upload/upload_config_loader.py
"""
上传配置加载器 —— 从 YAML 读取文件类型白名单及各自大小上限。

本模块属于 app/config/upload/ 配置子模块。
UploadService 通过 UploadConfig 数据类接收参数，不感知配置来源。

配置来源：本目录下唯一的 YAML 文件。
加载失败时抛出异常（上传配置是核心安全策略，不做静默降级）。
"""

import os
from dataclasses import dataclass, field

from src.com.damon.ming.app.config._yaml import load_yaml


@dataclass(frozen=True)
class UploadConfig:
    """上传配置（纯数据类）。所有参数必须由 YAML 显式声明，无内置默认值。"""

    # sha256 内存缓存 LRU 上限（超出时淘汰最久未用条目）
    sha_cache_max: int

    # 单次上传最大文件数
    max_files_per_request: int

    # 单次请求总大小上限（所有文件合计，字节）
    max_total_upload_size: int

    # 文件类型配置：扩展名(小写, 无点号) → {max_size_bytes, description}
    allowed_types: dict[str, dict] = field(default_factory=dict)

    def get_max_size_for_ext(self, ext: str) -> int | None:
        """获取某扩展名的文件大小上限。

        Args:
            ext: 扩展名（带点号，如 ".pdf"）

        Returns:
            该类型的字节上限。扩展名不在白名单时返回 None。
        """
        ext_clean = ext.lstrip(".").lower()
        type_cfg = self.allowed_types.get(ext_clean)
        if type_cfg is None:
            return None
        return type_cfg.get("max_size_bytes")

    def is_type_allowed(self, ext: str) -> bool:
        """检查扩展名是否在白名单中。

        Args:
            ext: 扩展名（带点号，如 ".pdf"）

        Returns:
            True 表示允许上传该类型。
        """
        ext_clean = ext.lstrip(".").lower()
        return ext_clean in self.allowed_types


class UploadConfigLoader:
    """从 YAML 文件加载上传配置。

    用法：
        cfg = UploadConfigLoader().load()
    """

    def __init__(self):
        self._config_dir = os.path.dirname(os.path.abspath(__file__))

    def load(self) -> UploadConfig:
        """加载上传配置。

        返回: UploadConfig 数据类实例。
        加载失败时抛出异常（上传配置是安全策略，不做静默降级）。
        """
        raw = self._read_yaml()

        sha_cache_max = raw.get("sha_cache_max")
        if not sha_cache_max or not isinstance(sha_cache_max, int) or sha_cache_max < 1:
            raise ValueError(
                f"上传配置中 sha_cache_max 必须为正整数 | dir={self._config_dir}"
            )

        max_files = raw.get("max_files_per_request")
        if not max_files or not isinstance(max_files, int) or max_files < 1:
            raise ValueError(
                f"上传配置中 max_files_per_request 必须为正整数 | dir={self._config_dir}"
            )

        allowed_types = raw.get("allowed_types", {})
        if not allowed_types:
            raise ValueError(
                f"上传配置中 allowed_types 不能为空 | dir={self._config_dir}"
            )

        max_total = raw.get("max_total_upload_size")
        if not max_total or not isinstance(max_total, int) or max_total < 1:
            raise ValueError(
                f"上传配置中 max_total_upload_size 必须为正整数 | dir={self._config_dir}"
            )

        return UploadConfig(
            sha_cache_max=sha_cache_max,
            max_files_per_request=max_files,
            max_total_upload_size=max_total,
            allowed_types=allowed_types,
        )

    def _read_yaml(self) -> dict:
        return load_yaml(self._config_dir)
