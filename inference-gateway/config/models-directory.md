# inference-gateway/config/models-directory.md
# 模型目录结构 —— 所有 AI 模型统一在 /root/ming/models/ 下
#
# Docker 挂载: /root/ming/models → /models（所有容器统一入口）
#
# 首次部署前在宿主机执行以下命令创建目录结构：
#
#   mkdir -p /root/ming/models/inference
#   mkdir -p /root/ming/models/embedding
#   mkdir -p /root/ming/models/rerank
#
# 目录结构：
# /root/ming/models/
# ├── inference/              ← vLLM / Ollama 推理模型（GGUF 或 HF 格式）
# │   ├── Qwen2.5-7B-Instruct/
# │   ├── Qwen2.5-0.5B-Instruct/
# │   ├── Qwen2.5-1.8B-Instruct/
# │   └── Qwen2.5-1.5B-Instruct/
# ├── embedding/              ← Embedding 模型（HuggingFace Hub 下载到此）
# │   └── BAAI/
# │       └── bge-m3/
# └── rerank/                 ← Rerank 模型（本地路径）
#     ├── bge-reranker-v2-gemma/
#     └── bge-reranker-v2-m3/
#
# 下载方式：
#   - vLLM 模型: 手动下载或 hf-cli 下载到 /root/ming/models/inference/
#   - Ollama 模型: ollama pull 命令（存储在 /root/ming/ollama/.ollama/，独立挂载）
#   - Embedding: 首次启动自动从 HF Hub 下载到 /models/embedding/
#   - Rerank: 手动下载到 /root/ming/models/rerank/
