# AI Fullstack System

单体仓库，包含后端、前端、推理网关三个子系统。

## 目录结构

```
ai-fullstack-system/
├── docker-compose.yaml      # 根入口：一键部署（include 聚合下面 3 个子文件）
├── app-server/              # FastAPI 后端 + PostgreSQL
│   └── docker-compose.yaml  # 后端 + 数据库（可独立构建）
├── web-app/                 # React 前端
│   └── docker-compose.yaml  # 前端（可独立构建）
├── inference-gateway/       # 推理路由网关 + 推理后端
│   └── docker-compose.yaml  # 网关（可独立构建）
└── scripts/                 # 部署辅助脚本
```

## docker-compose 说明

所有 4 个文件都叫 `docker-compose.yaml`，这是 Docker Compose 的标准约定名，
位于不同目录下不会冲突——`docker compose` 永远只读当前工作目录的那一个。

| 文件 | 职责 | 独立运行 |
|------|------|----------|
| 根目录 `docker-compose.yaml` | 聚合部署入口（`include` 引用子文件） | ✅ 推荐 |
| `app-server/docker-compose.yaml` | 后端服务 + PostgreSQL | ✅ |
| `web-app/docker-compose.yaml` | 前端 Nginx | ✅ |
| `inference-gateway/docker-compose.yaml` | 网关 + 推理后端容器 | ✅ |

## 部署方式

### 一键部署（推荐）

```bash
# 默认使用 Ollama 作为推理后端
docker compose up -d --build

# 使用 vLLM 推理后端
INFERENCE_SERVER=vllm docker compose up -d --build

# 停止所有服务
docker compose down
```

### 开发模式构建

```bash
SERVER_BUILD_ENV=1 FRONTEND_BUILD_ENV=1 docker compose up -d --build
```

### 单独构建某个模块

```bash
cd app-server && docker compose up -d --build
cd web-app && docker compose up -d --build
cd inference-gateway && docker compose up -d --build
```

## 推理后端切换

通过 `INFERENCE_SERVER` 环境变量统一控制：

- `ollama`（默认）— 轻量本地推理
- `vllm` — 高性能推理集群
