# app-server/src/com/damon/ming/app/app_state.py
"""
应用级状态 —— 进程内单例子系统，按语义分组挂在 app.state 上。

设计：
  - 与 request.state 的 ctx / client / encryption 同一套分组思路：
    启动时单次装配、全进程共享、按「谁拥有它」分组
  - AppInitializer.attach_to_app() 构造各分组实例后挂到 app.state
  - 消费方通过 request.app.state.<分组>.<字段> 读取，不再平铺

分组：
  config      配置快照（启动时从 YAML 装载，运行期只读）
  ai          AI 子系统运行时（RAG / 推理）
  threads     全局线程池运行时（跨 RAG、数据库等模块共享）
  storage     持久化
  encryption  加密

app.state.limiter 保持扁平：slowapi 框架硬编码读写该键
（extension.py 写入、middleware.py 读取），分组会让限流装饰器失效。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncio

    from src.com.damon.ming.ai.inference.inference_gateway import InferenceGateway
    from src.com.damon.ming.ai.rag.rag_tool import RagChoreographer
    from src.com.damon.ming.app.config.ai.rag.config import (
        LocaleConfig,
    )
    from src.com.damon.ming.app.config.system.system_config_loader import SystemConfig
    from src.com.damon.ming.app.config.upload.upload_config_loader import UploadConfig
    from src.com.damon.ming.app.encryption.session_service import SessionService
    from src.com.damon.ming.db.db_connection import DbConnection
    from src.com.damon.ming.encryption.v1.field_encryptor import FieldEncryptor
    from src.com.damon.ming.thread.pool_manager import ThreadPoolManager


@dataclass
class AppConfig:
    """配置快照 —— 启动时从 YAML 装载，运行期只读。"""

    system_config: SystemConfig
    upload_config: UploadConfig


@dataclass
class ThreadRuntime:
    """进程级线程池管理器，供各业务模块共享。"""

    pool_mgr: ThreadPoolManager


@dataclass
class RagRuntime:
    """RAG 容器及流程配置。"""

    rag_sem: asyncio.Semaphore
    execution_timeout_seconds: float
    retry_ms: int
    model_root_dir: str
    locales: dict[str, LocaleConfig]
    choreographer: RagChoreographer


@dataclass
class InferenceRuntime:
    """统一推理入口。"""

    gateway: InferenceGateway


@dataclass
class AIRuntime:
    """进程级 AI 子系统。"""

    rag: RagRuntime
    inference: InferenceRuntime


@dataclass
class Storage:
    """持久化。"""

    db_conn: DbConnection


@dataclass
class EncryptionState:
    """加密。"""

    session_service: SessionService
    field_encryptor: FieldEncryptor
    sign_context: bytes
