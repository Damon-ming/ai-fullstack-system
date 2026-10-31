# AI Fullstack System

基于知识库的 AI 问答全栈系统 — 多用户并发、端到端加密、多推理后端切换。

## 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                      客户端浏览器                         │
│         React SPA (Tailwind + TanStack Query)           │
│                   RSA + AES-GCM 加密                     │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTPS
                      ▼
┌─────────────────────────────────────────────────────────┐
│                  Nginx (web-app)                        │
│              前端静态资源 + 反向代理                      │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│               FastAPI 后端 (app-server)                  │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────┐ │
│  │ 加密中间件│ │ 速率限制 │ │ 输入验证 │ │ 多语言 i18n │ │
│  └─────────┘ └──────────┘ └──────────┘ └─────────────┘ │
│  ┌─────────────────────────────────────────────────────┐│
│  │              RAG Pipeline (RAGContainer)             ││
│  │  检索(Dense+Sparse+Hybrid) → 重排 → LLM 推理        ││
│  └─────────────────────────────────────────────────────┘│
│  线程池: document_pool / retrieval_pool / rerank_pool    │
│  信号量: infer_sem=16 / rag_sem=3 / guardrail_sem=2     │
└──────────┬──────────────────┬───────────────────────────┘
           │                  │
           │ HTTP             │ 文件上传 / 知识库管理
           │                  ▼
           ▼           ┌─────────────┐
┌──────────────────┐   │ PostgreSQL  │
│ Inference Gateway│   │  + pgvector │
│  按 api_key 路由  │   │ 用户/会话/  │
│  流式 SSE 透传    │   │ 历史/审计   │
│  重试 + 错误兜底  │   └─────────────┘
└────────┬─────────┘
         │
    ┌────┴────┬────────┬────────┬────────┐
    ▼         ▼        ▼        ▼        ▼
 vllm-1    vllm-2   vllm-3   vllm-4   vllm-5
 7B-chat   0.5B     1.8B     1.5B     4B-guardrail
 (意图)   (检索)    (改写)   (摘要)    (护栏)
```

## 核心特性

- **端到端加密**：RSA-OAEP + AES-GCM，HMAC-SHA256 签名，nonce 重放防护
- **多用户并发**：三层并发控制（信号量 + 模块锁 + 线程池），多用户共享知识库
- **混合检索**：Dense (pgvector) + Sparse (BM25) + Hybrid，section 级去重
- **推理后端热切换**：Ollama / vLLM / SGLang，改环境变量即可
- **多语言 i18n**：react-i18next 前端 + 后端 X-Language 协商
- **流式 SSE**：W3C EventSource 协议，start/delta/done/error 事件
- **护栏系统**：独立小模型实时安全检测，超时 fail-open

## 目录结构

```
ai-fullstack-system/
├── docker-compose.yaml          # 一键部署入口（include 聚合）
├── .env                         # 环境变量（不入库）
├── .env.example                 # 环境变量模板
├── app-server/                  # FastAPI 后端
│   ├── Dockerfile
│   ├── docker-compose.yaml
│   ├── requirements.txt
│   └── src/com/damon/ming/
│       ├── ai/                  # AI 模块（RAG + 推理）
│       │   ├── config/          # AI 配置加载器
│       │   ├── inference/       # 推理引擎（Ollama/vLLM/LiteLLM）
│       │   ├── registry/        # 引擎自注册
│       │   ├── retriever/       # 检索器（Dense/Sparse/Hybrid）
│       │   └── rag_tool.py      # RAGContainer 主入口
│       ├── app/                 # 应用配置 + 初始化
│       │   ├── config/          # YAML 配置加载器
│       │   └── app_initializer.py
│       ├── db/                  # 数据库连接池
│       ├── encryption/          # 加密体系
│       │   ├── globals.py       # 全局密钥注入
│       │   ├── v1/              # 纯加密原语（AES/RSA/HMAC）
│       │   └── session_service.py
│       ├── exception/           # 统一错误码
│       ├── i18n/                # 多语言模块
│       ├── middleware/          # 中间件（加密/限流）
│       ├── router/              # 路由层
│       │   ├── account/         # 账号体系
│       │   ├── chat/            # 聊天 + SSE
│       │   ├── encryption/      # 密钥交换
│       │   ├── history/         # 对话历史
│       │   ├── knowledge/       # 知识库目录
│       │   └── upload/          # 文件上传
│       ├── schemas/             # 请求/响应 Schema
│       ├── thread/              # 线程池管理器
│       ├── utils/               # 工具函数
│       └── vector_db/           # PGVector 存储
├── inference-gateway/           # 推理网关
│   ├── Dockerfile
│   ├── docker-compose.yaml
│   ├── gateway.py               # 路由代理（190 行）
│   ├── config/
│   │   ├── gateway.yaml         # 路由表
│   │   └── docker/
│   │       ├── docker-vllm.yaml # vLLM 实例编排
│   │       └── docker-ollama.yaml
│   └── requirements.txt
├── web-app/                     # React 前端
│   ├── Dockerfile
│   ├── docker-compose.yaml
│   ├── nginx.conf
│   ├── package.json
│   └── src/
└── scripts/                     # 部署辅助脚本
```

## 部署环境要求

### 软件依赖

| 组件 | 最低版本 | 说明 |
|------|---------|------|
| Docker Engine | 20.10+ | 容器运行时 |
| Docker Compose | v2.0+ | 编排工具（`docker compose` 非 `docker-compose`） |
| NVIDIA Driver | 525+ | vLLM 模式需要 |
| NVIDIA Container Toolkit | v1.14+ | GPU 容器调度 |

### 硬件要求（Ollama 模式）

| 资源 | 最低 | 推荐 | 说明 |
|------|------|------|------|
| CPU | 4 核 | 8 核+ | 推理 + 检索 + 嵌入 |
| 内存 | 8 GB | 16 GB+ | 7B 模型约需 6GB |
| 磁盘 | 20 GB | 50 GB+ | 模型 + 知识库 + 日志 |

### 硬件要求（vLLM 模式）

| 资源 | 最低 | 推荐 | 说明 |
|------|------|------|------|
| GPU | 1× 16GB VRAM | 5× 16GB+ VRAM | 5 个独立推理实例 |
| GPU 型号 | RTX 3090 / A4000 | A100 / H100 | 支持 CUDA + Tensor Core |
| CPU | 8 核 | 16 核+ | 多路推理调度 |
| 内存 | 32 GB | 64 GB+ | 5 个模型实例共享 |
| 磁盘 | 100 GB | 200 GB+ | 5 个模型权重 + 知识库 |

### GPU 显存分配（vLLM 模式）

| 实例 | 模型 | gpu-memory-utilization | 预估显存 |
|------|------|----------------------|----------|
| vllm-pool-1 | Qwen2.5-7B-Instruct | 0.7 | ~11 GB |
| vllm-pool-2 | Qwen2.5-0.5B-Instruct | 0.3 | ~3 GB |
| vllm-pool-3 | Qwen2.5-1.8B-Instruct | 0.4 | ~5 GB |
| vllm-pool-4 | Qwen2.5-1.5B-Instruct | 0.4 | ~5 GB |
| vllm-pool-5 | Qwen3Guard-Gen-4B | 0.3 | ~5 GB |
| **合计** | | | **~29 GB** |

### 宿主机目录结构

```
${DATA_DIR}/                          # 默认 /root/damon
├── postgres/                         # PostgreSQL 数据目录
├── ollama/.ollama/                   # Ollama 模型缓存（ollama 模式）
├── models/                           # vLLM 模型权重（vLLM 模式）
│   └── inference/
│       ├── Qwen2.5-7B-Instruct/
│       ├── Qwen2.5-0.5B-Instruct/
│       ├── Qwen2.5-1.8B-Instruct/
│       ├── Qwen2.5-1.5B-Instruct/
│       └── Qwen3Guard-Gen-4B/
├── chroma/                           # Chroma 向量缓存
├── knowledges/                       # 上传知识库文件
└── logs/
    └── app-server/                   # 后端运行日志
```

### 容器镜像

| 服务 | 基础镜像 | Python | 说明 |
|------|---------|--------|------|
| app-server | python:3.11-slim | 3.11 | FastAPI 后端 |
| inference-gateway | python:3.11-slim | 3.11 | 推理网关 |
| web-app (builder) | node:22-alpine | — | 前端构建 |
| web-app (serve) | nginx:alpine | — | 前端静态资源 |
| postgres | postgres:16-alpine | — | 数据库 |
| ollama | ollama/ollama:0.32.14 | — | Ollama 后端 |
| vllm-{1-5} | vllm/vllm-openai:latest | — | 推理实例 |

### 健康检查

所有服务均配置 healthcheck：

| 服务 | 检查方式 | 间隔 | 超时 | 重试 | 启动宽限期 |
|------|---------|------|------|------|-----------|
| postgres | `pg_isready` | 5s | 3s | 10 | 10s |
| app-server | `GET /ping` | 10s | 5s | 5 | 30s |
| inference-gateway | `GET /docs` | 10s | 5s | 3 | — |
| vllm-pool-{1-5} | `GET /health` | 15s | 10s | 3 | 120~300s |

vLLM 实例的 `start_period` 根据模型大小设定（7B 模型 300s，小模型 120s），确保模型加载期间不被判定为不健康。

### 启动顺序

```
postgres (healthy)
    ↓
inference-gateway (healthy) ←── vllm-pool-{1-5} 独立启动，无 depends_on
    ↓
app-server (depends_on: postgres + inference-gateway)
    ↓
web-app (depends_on: app-server)
```

vLLM 实例不参与 Docker `depends_on`——它们通过 gateway 的 api_key 路由注册，启动时间由 gateway 的路由表决定，不阻塞其他服务启动。

## 一键部署

### 前置条件

- Docker Engine 20.10+
- Docker Compose v2.0+
- NVIDIA Container Toolkit（vLLM 模式需要）

### 部署步骤

```bash
# 1. 克隆项目
git clone <repo-url> && cd ai-fullstack-system

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，设置 DB_PASSWORD、MASTER_KEY 等

# 3. 部署（Ollama 模式，适合开发）
docker compose up -d --build

# 4. 或部署 vLLM 模式（生产，需要 GPU）
INFERENCE_SERVER=vllm docker compose up -d --build

# 5. 查看日志
docker compose logs -f app-server

# 6. 停止所有服务
docker compose down
```

### 端口分配

| 宿主机端口 | 服务 | 容器内端口 | 说明 |
|-----------|------|-----------|------|
| 80 | web-app | 80 | 前端入口 |
| 5432 | postgres | 5432 | 数据库（可选暴露） |
| 11434 | ollama-server | 11434 | Ollama 直连（ollama 模式） |

以下仅容器内访问（不映射宿主机）：
- `8000` — app-server
- `8080` — inference-gateway
- `8000×5` — vllm-pool-1 ~ 5

## 推理后端切换

通过 `INFERENCE_SERVER` 环境变量统一控制：

| 值 | 适用场景 | 需要 GPU |
|---|---|---|
| `ollama`（默认） | 本地开发 / 轻量部署 | ❌ |
| `vllm` | 高性能生产 | ✅ |
| `sglang` | 预留扩展 | ✅ |

切换只需改 `.env` 后重新 `docker compose up -d --build`。

## API 概览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/account/login/v1` | 登录获取 token |
| POST | `/api/encryption/key/v1` | 获取 RSA 公钥 |
| POST | `/api/encryption/session/v1` | 注册 AES 会话 |
| POST | `/api/chat/send/v1` | 非流式聊天 |
| POST | `/api/chat/chat/v1` | 流式聊天（SSE） |
| GET | `/api/history/list/v1` | 历史记录列表 |
| GET | `/api/history/v1/{id}` | 历史记录详情 |
| POST | `/api/history/save/v1` | 保存对话历史 |
| DELETE | `/api/history/v1/{id}` | 删除历史记录 |
| GET | `/api/knowledge/tree/v1` | 知识库目录树 |
| POST | `/api/files/upload/v1` | 文件上传 |

所有加密请求需携带：
- `Authorization: Bearer <token>`
- `X-Encrypt-Version: <supported-version>`
- `X-Session-ID: <session_id>`
- `X-Timestamp`, `X-Nonce`, `X-Signature`

## 安全设计

| 层面 | 实现 |
|------|------|
| 传输加密 | RSA-OAEP-2048 + AES-256-GCM + HMAC-SHA256 |
| 签名防重放 | nonce 缓存（10min TTL，LRU 10000 上限） |
| 会话绑定 | session_id = (token + device_id)，加密密钥与设备绑定 |
| 速率限制 | slowapi 全端点 per-IP 限流 |
| 输入验证 | 独立护栏模型，超时 fail-open |
| 数据隔离 | 多用户共享知识库，对话历史按 token 隔离 |
| 审计日志 | 上传操作记录到 upload_records 表 |

## 配置说明

所有配置通过 YAML 文件管理，零硬编码：

| 配置 | 路径 | 说明 |
|------|------|------|
| 系统配置 | `config/system/` | knowledge_dir 等路径 |
| 数据库 | `config/db/` | 连接池参数 |
| 推理运行时 | `config/inference/inference-runtime.yaml` | 模型参数 + 并发控制 |
| 加密 | `config/encryption/` | RSA 密钥大小、TTL |
| i18n | `config/i18n/` | 默认语言、支持语言列表 |
| 上传 | `config/upload/` | 文件类型白名单、大小限制 |
| 线程池 | `config/thread/` | 各池大小 |
| 网关路由 | `inference-gateway/config/gateway.yaml` | api_key → upstream 映射 |

环境变量覆盖：
- `INFERENCE_SERVER` — 推理后端选择
- `INFERENCE_API_KEYS` — 各角色 api_key JSON
- `INFERENCE_GATEWAY_URL` — 网关地址
- `DB_PASSWORD` / `MASTER_KEY` — 敏感凭据

## 开发指南

### 后端（app-server）

```bash
cd app-server
pip install -r requirements.txt
# 启动前确保 PostgreSQL 运行并配置 .env
python -m src.com.damon.ming.main
```

### 前端（web-app）

```bash
cd web-app
pnpm install
pnpm dev          # 开发服务器
pnpm build        # 生产构建
```

### 网关（inference-gateway）

```bash
cd inference-gateway
pip install -r requirements.txt
python gateway.py
```

### 添加新推理后端

1. 新建 `inference-gateway/config/docker/docker-{name}.yaml`（容器编排）
2. `gateway.yaml` 添加路由条目
3. `.env` 设置 `INFERENCE_API_KEYS` 映射
4. `inference-runtime.yaml` 添加 roles 参数
5. `INFERENCE_SERVER={name}` 部署

## 并发控制模型

三层隔离设计，避免多用户请求互相阻塞：

### 第 1 层：信号量（asyncio.Semaphore）

| 信号量 | 默认值 | 保护目标 |
|--------|--------|----------|
| `infer_sem` | 16 | LLM 推理调用（主推理 + 摘要/压缩共享） |
| `rag_sem` | 3 | RAG 检索阶段（反压控制） |
| `guardrail_sem` | 2 | 护栏 LLM 调用（4B 小模型，2 足够） |

信号量在 `lifespan` 内创建，绑定到正确的事件循环。RAG 和推理信号量嵌套使用：RAG 先释放信号量，推理再获取，避免 RAG 等待期间占用推理槽位。

### 第 2 层：模块级锁

| 锁 | 类型 | 保护目标 |
|----|------|----------|
| `_build_lock` | `threading.Lock` | BM25 索引原子替换 |
| `_nonce_cache_lock` | `asyncio.Lock` | nonce 重放缓存一致性 |
| CrossEncoder 批次锁 | `threading.Lock` | 重排模型 per-batch 隔离 |
| BM25 检索锁 | `threading.Lock` | 检索查询快照一致性 |

### 第 3 层：线程池隔离

```
ThreadPoolManager（进程单例）
├── retrieval  pool(4)    ← HybridRetriever 稠密+稀疏并发
├── document   pool(8)    ← PDF 加载 / 文档分割
├── inference  pool(2)    ← 推理辅助线程
├── rerank     pool(2)    ← CrossEncoder 重排专用（与 retrieval 隔离）
└── bm25       pool(1)    ← BM25 全量重建（串行，防检索池饿死）
```

各 AI 模块从 `ThreadPoolManager` 获取命名线程池，不自行创建。同步 I/O（DB 查询、文件读写、BM25 计算）通过 `loop.run_in_executor()` 丢进线程池，不阻塞事件循环。

## RAG 流水线

```
用户查询
   │
   ▼
[Phase 0] 输入校验（纯本地规则，零 IO，微秒级）
   │ 不通过 → 直接返回错误
   ▼
[Phase 1] 护栏检测（独立超时 5s，guardrail_sem=2，超时 fail-open）
   │ 不通过 → 返回护栏拦截
   ▼
[Phase 2] RAG 检索（rag_sem=3，total_timeout=30s 预算内）
   │
   ├── Dense 检索（pgvector 余弦相似度）
   ├── Sparse 检索（BM25 + jieba 中文分词）
   └── Hybrid 融合（oversample → section 级去重 → rerank）
   │
   ▼
[Phase 3] 上下文构造
   │ system prompt（纯净指令）+ user message（参考资料 + 问题）
   │ 参考资料标签与系统 prompt 分离，防模板注入
   ▼
[Phase 4] LLM 推理（infer_sem=16）
   │ LiteLLM / Ollama / vLLM 后端
   │ 结构化 JSON 输出（Pydantic schema 约束）
   ▼
响应组装（SSE delta 事件流 / 非流式完整 JSON）
```

## 加密协议

### 密钥交换流程

```
客户端                              服务端
  │                                   │
  ├── GET /api/encryption/key/v1 ───→ │
  │←──── RSA 公钥 (PEM) ──────────────┤
  │                                   │
  │  生成 AES-256 密钥                 │
  │  RSA-OAEP 加密 AES 密钥            │
  │                                   │
  ├── POST /api/encryption/session ──→│
  │  { encryptedAesKey, session_id }  │
  │                                   ├── RSA 解密 → AES 密钥
  │                                   ├── 生成 key_id
  │                                   ├── 内存表 + DB 原子写入
  │                                   └── 撤销同一 session_id 旧密钥
  │←──── { keyId, expiresIn } ────────┤
  │                                   │
  │  后续请求：AES-GCM 加密 body       │
  │  + HMAC-SHA256 签名               │
  │  + nonce 重放防护                 │
```

### 请求签名

```
签名内容 = 解密后的 body (排除 signature/timestamp/nonce)
签名密钥 = HKDF(session.aes_key, sign_context)
签名头：
  X-Timestamp: 当前时间戳（5min 有效期）
  X-Nonce:     随机 nonce（10min LRU 去重）
  X-Signature: HMAC-SHA256(params, signing_key)
```

### 错误码体系

9 位分段式数字码：`A BB CCC DDD`

| 位 | 含义 | 示例 |
|----|------|------|
| A (第1位) | 结果位 | 1=成功, 2=失败 |
| BB (2-3位) | 系统位 | 00=当前服务 |
| CCC (4-6位) | 业务模块 | 002=加密, 003=认证, 005=Chat |
| DDD (7-9位) | 具体错误 | 001=超时, 002=格式错误 |

```
100000000 = 成功
200002001 = 加密模块 — AES 密钥格式错误
200002006 = 加密模块 — 会话过期/无效
200002009 = 加密模块 — 请求重放拦截
200002010 = 加密模块 — 空 nonce 拒绝
200003001 = 认证模块 — 缺少 Token
200005001 = Chat 模块 — 请求超时
200007001 = 系统 — 数据库故障
200007007 = 系统 — 文件系统故障
```

## SSE 协议

W3C EventSource 标准格式，事件流：

```
event: start                    ← 连接建立，立即发送（信号量外）
data: {"model": "Qwen2.5-7B"}

event: delta                    ← LLM 逐 token 输出
data: {"content": "你好"}

event: reasoning                ← 思考过程（reasoning 模型）
data: {"content": "让我想想..."}

event: delta
data: {"content": "，"}

event: done                     ← 结束包
data: {}

event: error                    ← 异常时替代 done
data: {"code": 200005001, "message": "请求超时"}
```

所有错误路径（校验失败、护栏拦截、超时、未知异常）都通过 SSE error 事件返回，不裸断连。

## 技术栈

| 层 | 技术 |
|----|------|
| 前端 | React 18 + TypeScript + Tailwind CSS v4 + TanStack Query |
| 后端 | FastAPI + SQLAlchemy + Pydantic |
| 数据库 | PostgreSQL + pgvector |
| 检索 | BM25 + HuggingFace Embedding + Hybrid |
| 推理 | Ollama / vLLM / SGLang（可切换） |
| 加密 | cryptography (RSA-OAEP + AES-GCM + HMAC) |
| 部署 | Docker Compose + Nginx |
| i18n | react-i18next + 后端 X-Language 协商 |
| 限流 | slowapi |

## License

MIT
