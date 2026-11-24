# model-gateway/config/models-directory.md
# 模型目录结构 —— 宿主机模型文件统一在 DATA_DIR/models/ 下
#
# Docker 挂载: ${DATA_DIR}/models → ${MODEL_ROOT_DIR}
#
# 首次部署前在宿主机执行以下命令创建目录结构：
#
#   mkdir -p <DATA_DIR>/models/inference
#   mkdir -p <DATA_DIR>/models/embedding
#   mkdir -p <DATA_DIR>/models/rerank
#
# 目录结构：
# <DATA_DIR>/models/
# ├── inference/              ← vLLM 推理模型（HuggingFace 格式）
# │   ├── Qwen2.5-0.5B-Instruct/
# │   ├── Qwen2.5-1.8B-Instruct/
# │   └── Qwen3Guard-Gen-0.6B/
# ├── embedding/              ← Embedding 模型（HuggingFace Hub 下载到此）
# │   └── BAAI/
# │       └── bge-m3/
# └── rerank/                 ← Rerank 模型（本地路径）
#     └── bge-reranker-v2-m3/
#
# 下载方式：
#   - 项目根目录安装 huggingface-hub 后，运行 python scripts/download-models.py，
#     会按 .env 中的 DATA_DIR 下载当前部署需要的模型。
