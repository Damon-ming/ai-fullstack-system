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
  ai          AI 能力（推理引擎 / RAG / 线程池）
  guardrail   护栏（引擎 + 并发 + 超时）
  chat        聊天链路运行时（并发 / 超时 / 重试 / 多 locale 文案）
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

    from src.com.damon.ming.ai.guardrail.base_guardrail import BaseGuardrail
    from src.com.damon.ming.ai.inference.base_inference import BaseInferenceService
    from src.com.damon.ming.ai.rag_tool import RAGContainer
    from src.com.damon.ming.app.config.inference.inference_runtime_config_loader import (
        LocaleConfig,
    )
    from src.com.damon.ming.app.config.system.system_config_loader import SystemConfig
    from src.com.damon.ming.app.config.upload.upload_config_loader import UploadConfig
    from src.com.damon.ming.app.encryption.session_service import SessionService
    from src.com.damon.ming.db.db_connection import DbConnection
    from src.com.damon.ming.thread.pool_manager import ThreadPoolManager


@dataclass
class AppConfig:
    """配置快照 —— 启动时从 YAML 装载，运行期只读。"""

    system_config: SystemConfig
    upload_config: UploadConfig


@dataclass
class AiServices:
    """AI 能力 —— 推理引擎 / RAG / 线程池。

    组名取 ai 而非 inference：线程池服务于检索、重排、文档解析等整条 AI
    链路，"inference" 只涵盖模型推理那一段。与代码库模块名 src/com/damon/ming/ai/
    保持一致。pool_mgr 归此组：它是 RAGContainer 的线程池持有者，upload 只是
    借用 document 池做文档解析，并非聊天专属。
    """

    infer_service: BaseInferenceService
    rag_app: RAGContainer
    model_name: str
    options: dict
    pool_mgr: ThreadPoolManager


@dataclass
class GuardrailState:
    """护栏 —— 引擎 + 并发 + 超时。"""

    engine: BaseGuardrail
    sem: asyncio.Semaphore
    timeout: int


@dataclass
class ChatRuntime:
    """聊天链路运行时 —— 并发 / 超时 / 重试 / 多 locale 文案。

    字段名去掉了与分组名重复的前缀：chat_sem → sem、chat_timeout → timeout，
    与 request_context.py 中 ClientContext.token（而非 client_token）同一约定。
    rag_sem 保留 rag_ 前缀：与 sem 是两个不同用途的信号量，需要区分。
    """

    sem: asyncio.Semaphore
    rag_sem: asyncio.Semaphore
    timeout: int
    retry_ms: int
    locales: dict[str, LocaleConfig]


@dataclass
class Storage:
    """持久化。"""

    db_conn: DbConnection


@dataclass
class EncryptionState:
    """加密。"""

    session_service: SessionService
    sign_context: bytes
