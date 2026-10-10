"""环境变量启动校验 —— 缺失关键配置时返回错误列表。"""

import os

from src.com.damon.ming.log import pin

logger = pin("app.precheck")


def _check_signature_secret(is_debug: bool) -> list[str]:
    """检查 SIGNATURE_SECRET 是否设置。"""
    errors = []
    sig_secret = os.environ.get("SIGNATURE_SECRET", "")

    if not sig_secret:
        # 尝试从 YAML 配置读取
        try:
            from src.com.damon.ming.encryption import EncryptionConfigLoader

            config = EncryptionConfigLoader().load(
                profile="debug" if is_debug else "production"
            )
            if not config.signature_secret:
                errors.append(
                    "SIGNATURE_SECRET 未设置（环境变量或 encryption-config.yaml）"
                )
        except Exception:
            errors.append(
                "SIGNATURE_SECRET 未设置（环境变量或 encryption-config.yaml）"
            )

    return errors


def _check_master_key(is_debug: bool) -> list[str]:
    """检查 MASTER_KEY 是否设置。

    开发环境未设置时自动生成（不报错）。
    生产环境必须设置。
    """
    errors = []
    master_key = os.environ.get("MASTER_KEY", "")

    if not master_key and not is_debug:
        errors.append("MASTER_KEY 未设置（生产环境必须通过密钥管理系统注入）")

    return errors


def _check_database(is_debug: bool) -> list[str]:
    """检查数据库配置是否可用。

    开发环境可降级为纯内存（不报错）。
    生产环境必须有数据库（环境变量 DB_CONNECTION 或 YAML 配置文件）。
    """
    errors = []

    if is_debug:
        return errors

    # 环境变量 DB_CONNECTION
    db_url = os.environ.get("DB_CONNECTION", "")
    if db_url:
        return errors

    # YAML 配置文件
    try:
        from src.com.damon.ming.db import DbConfigLoader

        loader = DbConfigLoader()
        db_config = loader.load(profile="production")
        if db_config.get_connection_string():
            return errors
    except Exception:
        pass

    errors.append(
        "数据库未配置（生产环境必须设置 DB_CONNECTION 环境变量或 db/db-config.yaml）"
    )
    return errors


def run_precheck(is_debug: bool) -> list[str]:
    """执行所有启动前校验，返回错误列表。

    无错误返回空列表。
    """
    logger.info("执行启动前环境校验 | debug=%s", is_debug)

    errors = []
    errors.extend(_check_signature_secret(is_debug))
    errors.extend(_check_master_key(is_debug))
    errors.extend(_check_database(is_debug))

    if errors:
        logger.error("环境校验失败：")
        for err in errors:
            logger.error("  • %s", err)
    else:
        logger.info("环境校验通过")

    return errors
