# app-server/src/com/damon/ming/app/config/upload/upload_config_loader.py
"""
上传配置加载器 —— 从 YAML 读取文件类型白名单及各自大小上限。

本模块属于 app/config/upload/ 配置子模块。
UploadService 通过 UploadConfig 数据类接收参数，不感知配置来源。

加载优先级：
  1. 显式传入的 config_path
  2. UPLOAD_CONFIG_PATH 环境变量
  3. 默认路径：本目录下的 upload-config.yaml

加载失败时抛出异常（上传配置是核心安全策略，不做静默降级）。
"""

import os
from dataclasses import dataclass, field

import yaml


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
        cfg = UploadConfigLoader("path/to/config.yaml").load()
    """

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            config_path = os.environ.get("UPLOAD_CONFIG_PATH", "")
        if not config_path:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(base_dir, "upload-config.yaml")
        self._config_path = config_path

    def load(self) -> UploadConfig:
        """加载上传配置。

        返回: UploadConfig 数据类实例。
        加载失败时抛出异常（上传配置是安全策略，不做静默降级）。
        """
        raw = self._read_yaml()
        upload_section = raw.get("upload", {})

        if not upload_section:
            raise ValueError(
                f"上传配置文件格式错误：缺少 'upload' 根节点 | path={self._config_path}"
            )

        sha_cache_max = upload_section.get("sha_cache_max")
        if not sha_cache_max or not isinstance(sha_cache_max, int) or sha_cache_max < 1:
            raise ValueError(
                f"上传配置中 sha_cache_max 必须为正整数 | path={self._config_path}"
            )

        max_files = upload_section.get("max_files_per_request")
        if not max_files or not isinstance(max_files, int) or max_files < 1:
            raise ValueError(
                f"上传配置中 max_files_per_request 必须为正整数 | path={self._config_path}"
            )

        allowed_types = upload_section.get("allowed_types", {})
        if not allowed_types:
            raise ValueError(
                f"上传配置中 allowed_types 不能为空 | path={self._config_path}"
            )

        max_total = upload_section.get("max_total_upload_size")
        if not max_total or not isinstance(max_total, int) or max_total < 1:
            raise ValueError(
                f"上传配置中 max_total_upload_size 必须为正整数 | path={self._config_path}"
            )

        return UploadConfig(
            sha_cache_max=sha_cache_max,
            max_files_per_request=max_files,
            max_total_upload_size=max_total,
            allowed_types=allowed_types,
        )

    def _read_yaml(self) -> dict:
        if not os.path.exists(self._config_path):
            raise FileNotFoundError(f"上传配置文件不存在: {self._config_path}")
        with open(self._config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)
        if not raw_cfg or not isinstance(raw_cfg, dict):
            raise ValueError("上传配置文件格式错误：需要顶层键值对")
        return raw_cfg
