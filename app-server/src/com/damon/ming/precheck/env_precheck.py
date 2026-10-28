"""环境变量启动校验 —— 缺失关键配置时返回错误列表。"""

import os

from src.com.damon.ming.log import pin

logger = pin("app.precheck")


def _check_master_key(is_debug: bool) -> list[str]:
    """检查 MASTER_KEY 是否设置。

    所有环境都必须通过 .env 设置 MASTER_KEY，不允许自动生成。
    生产环境（非 debug）：密钥长度必须 ≥32 字符。
    """
    errors = []
    master_key = os.environ.get("MASTER_KEY", "")

    if not master_key:
        errors.append("MASTER_KEY 未设置（所有环境必须通过 .env 注入）")
    elif not is_debug and len(master_key) < 32:
        errors.append(
            f"MASTER_KEY 长度不足（当前 {len(master_key)} 字符，生产环境要求 ≥32）"
        )

    return errors


def _check_encryption_config(is_debug: bool) -> None:
    """检查加密配置（YAML）中的必要字段是否填写。

    这些字段属于业务协议标识，encryption 模块不包含，必须由业务层配置。
    缺失任何一个字段都直接抛异常，不使用默认值降级——
    空的 salt/info/context 会导致加密/签名静默失败，比不启动更危险。
    """
    from src.com.damon.ming.app.config.encryption.encryption_config_loader import (
        EncryptionConfigLoader,
    )

    try:
        config = EncryptionConfigLoader().load(profile="common")
    except FileNotFoundError:
        raise RuntimeError(
            "加密配置文件不存在，启动终止。"
            "请确保 app/config/encryption/encryption-config.yaml 文件存在。"
        )
    except Exception as e:
        raise RuntimeError(f"加密配置文件加载失败，启动终止：{e}") from e

    missing = []
    if not config.sign_context:
        missing.append("sign_context")
    if not config.kek_salt:
        missing.append("kek_salt")
    if not config.kek_info:
        missing.append("kek_info")
    if not config.data_key_id:
        missing.append("data_key_id")

    if missing:
        raise RuntimeError(
            f"加密配置缺失必要字段，启动终止：{', '.join(missing)}。"
            f"请检查 app/config/encryption/encryption-config.yaml 的 common 剖面。"
        )


def _check_database(is_debug: bool) -> list[str]:
    """检查数据库配置是否可用。

    先检查环境变量（直接给出变量名提示），再加载完整配置。
    """
    errors = []

    # 环境变量预检：缺失时直接指出变量名，不用等到 DbConfigLoader 报错
    for env_key in ("DB_NAME", "DB_USER", "DB_PASSWORD"):
        if not os.environ.get(env_key):
            errors.append(f"数据库环境变量 {env_key} 未设置（请检查 .env 文件）")

    if errors:
        return errors

    try:
        from src.com.damon.ming.app.config.db.db_config_loader import DbConfigLoader

        loader = DbConfigLoader()
        db_config = loader.load(profile="common")
        if not db_config.url and not db_config.host:
            return [
                "数据库配置缺少连接信息（url 或 host），请检查 db-config.yaml 的 common 剖面"
            ]
    except FileNotFoundError as e:
        return [f"数据库配置文件不存在：{e}"]
    except Exception as e:
        return [f"数据库配置加载失败：{e}"]

    return []


def run_precheck(is_debug: bool) -> list[str]:
    """执行所有启动前校验。

    加密配置检查失败会直接抛异常（不可降级），其他检查返回错误列表。
    无错误返回空列表。
    """
    logger.info("执行启动前环境校验 | debug=%s", is_debug)

    # 加密配置：缺失直接终止，不返回错误列表（默认值会导致加密静默失败）
    _check_encryption_config(is_debug)

    errors = []
    errors.extend(_check_master_key(is_debug))
    errors.extend(_check_database(is_debug))

    if errors:
        logger.error("环境校验失败：")
        for err in errors:
            logger.error("  • %s", err)
    else:
        logger.info("环境校验通过")

    return errors
