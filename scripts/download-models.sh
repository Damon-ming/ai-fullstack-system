#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# scripts/download-models.sh —— 一键下载所有 AI 模型
#
# 用法：
#   bash scripts/download-models.sh                  # 下载全部
#   bash scripts/download-models.sh --vllm           # 仅 vLLM 推理模型
#   bash scripts/download-models.sh --embedding      # 仅 Embedding 模型
#   bash scripts/download-models.sh --rerank         # 仅 Rerank 模型
#   bash scripts/download-models.sh --ollama         # 仅 Ollama 模型（自动 pull）
#
# 环境变量：
#   MODELS_DIR   模型根目录（默认 /root/damon/models）
#   HF_ENDPOINT  镜像站（默认 https://hf-mirror.com，国内加速）
# ═══════════════════════════════════════════════════════════════════

set -euo pipefail

# ── 配置 ──────────────────────────────────────────────────────────
MODELS_DIR="${MODELS_DIR:-/root/damon/models}"
HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
HF_CLI="huggingface-cli"

# ── 颜色输出 ──────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── 工具检查 ──────────────────────────────────────────────────────
check_hf_cli() {
    if ! command -v "$HF_CLI" &>/dev/null; then
        log_info "huggingface-cli 未安装，正在安装..."
        pip install -q huggingface-hub[cli]
    fi
}

# ── 下载函数 ──────────────────────────────────────────────────────
download_hf_model() {
    local repo_id="$1"
    local local_dir="$2"
    local description="${3:-$repo_id}"

    if [ -d "$local_dir" ] && [ -n "$(ls -A "$local_dir" 2>/dev/null)" ]; then
        log_skip "$description（已存在）"
        return 0
    fi

    log_info "下载 $description..."
    log_info "  来源: $repo_id"
    log_info "  目标: $local_dir"

    HF_ENDPOINT="$HF_ENDPOINT" huggingface-cli download \
        "$repo_id" \
        --local-dir "$local_dir" \
        --local-dir-use-symlinks False \
        --resume-download

    log_ok "$description 下载完成"
}

# ── vLLM 推理模型 ─────────────────────────────────────────────────
download_vllm_models() {
    log_info "═══ vLLM 推理模型 ═══"

    local models=(
        "Qwen/Qwen2.5-7B-Instruct:inference/Qwen2.5-7B-Instruct:聊天主模型 (7B)"
        "Qwen/Qwen2.5-0.5B-Instruct:inference/Qwen2.5-0.5B-Instruct:意图识别模型 (0.5B)"
        "Qwen/Qwen2.5-1.8B-Instruct:inference/Qwen2.5-1.8B-Instruct:查询改写模型 (1.8B)"
        "Qwen/Qwen2.5-1.5B-Instruct:inference/Qwen2.5-1.5B-Instruct:摘要模型 (1.5B)"
    )

    for entry in "${models[@]}"; do
        IFS=':' read -r repo_id local_subdir desc <<< "$entry"
        download_hf_model "$repo_id" "$MODELS_DIR/$local_subdir" "$desc"
    done

    # Qwen3Guard 可能不存在于 HF，尝试下载
    local guard_dir="$MODELS_DIR/inference/Qwen3Guard-Gen-4B"
    if [ -d "$guard_dir" ] && [ -n "$(ls -A "$guard_dir" 2>/dev/null)" ]; then
        log_skip "护栏模型 Qwen3Guard-Gen-4B（已存在）"
    else
        log_warn "Qwen3Guard-Gen-4B 尝试下载（可能不存在于 HuggingFace）..."
        HF_ENDPOINT="$HF_ENDPOINT" huggingface-cli download \
            "Qwen/Qwen3Guard-Gen-4B" \
            --local-dir "$guard_dir" \
            --local-dir-use-symlinks False \
            --resume-download 2>/dev/null \
            || log_warn "Qwen3Guard-Gen-4B 下载失败，请手动下载到 $guard_dir"
    fi
}

# ── Embedding 模型 ────────────────────────────────────────────────
download_embedding_models() {
    log_info "═══ Embedding 模型 ═══"
    download_hf_model "BAAI/bge-m3" "$MODELS_DIR/embedding/BAAI/bge-m3" "BGE-M3 多语言嵌入"
}

# ── Rerank 模型 ───────────────────────────────────────────────────
download_rerank_models() {
    log_info "═══ Rerank 模型 ═══"
    download_hf_model "BAAI/bge-reranker-v2-gemma" "$MODELS_DIR/rerank/bge-reranker-v2-gemma" "BGE-Reranker v2 Gemma（中文主力）"
    download_hf_model "BAAI/bge-reranker-v2-m3" "$MODELS_DIR/rerank/bge-reranker-v2-m3" "BGE-Reranker v2 M3（轻量/降级）"
}

# ── Ollama 模型（通过 ollama pull）─────────────────────────────────
download_ollama_models() {
    log_info "═══ Ollama 模型 ═══"

    if ! command -v ollama &>/dev/null; then
        log_error "ollama 未安装，请先安装 Ollama: https://ollama.com/download"
        log_info "安装后启动服务: systemctl start ollama"
        return 1
    fi

    # 根据 inference-runtime.yaml 的角色，需要以下 Ollama 模型
    local models=(
        "qwen2.5:7b-instruct-q4_K_M:聊天主模型 (7B)"
        "qwen2.5:0.5b-instruct-q4_K_M:意图识别模型 (0.5B)"
        "qwen2.5:1.8b-instruct-q4_K_M:查询改写模型 (1.8B)"
        "qwen2.5:1.5b-instruct-q4_K_M:摘要模型 (1.5B)"
    )

    for entry in "${models[@]}"; do
        IFS=':' read -r model_tag desc <<< "$entry"
        log_info "Pull Ollama 模型: $model_tag ($desc)"
        ollama pull "$model_tag" && log_ok "$model_tag pull 完成" || log_error "$model_tag pull 失败"
    done
}

# ── 创建目录结构 ──────────────────────────────────────────────────
create_directories() {
    log_info "创建模型目录结构..."
    mkdir -p "$MODELS_DIR"/{inference,embedding/BAAI,rerank}
    log_ok "目录结构就绪: $MODELS_DIR"
}

# ── 磁盘空间检查 ──────────────────────────────────────────────────
check_disk_space() {
    local available_gb
    available_gb=$(df -BG "$MODEMS_DIR" 2>/dev/null | awk 'NR==2 {print $4+0}' || echo "0")
    # 全部模型约需 80-100GB
    log_info "模型根目录: $MODELS_DIR"
    if command -v df &>/dev/null; then
        local avail
        avail=$(df -h "$MODELS_DIR" 2>/dev/null | awk 'NR==2 {print $4}' || echo "未知")
        log_info "可用空间: $avail"
    fi
}

log_skip() { echo -e "${YELLOW}[SKIP]${NC}  $*"; }

# ── 主入口 ────────────────────────────────────────────────────────
main() {
    echo "══════════════════════════════════════════════════════════════"
    echo "  AI Fullstack System —— 模型一键下载"
    echo "  模型目录: $MODELS_DIR"
    echo "  HF 镜像:  $HF_ENDPOINT"
    echo "══════════════════════════════════════════════════════════════"
    echo ""

    check_disk_space
    create_directories

    local mode="${1:---all}"

    case "$mode" in
        --all)
            download_embedding_models
            download_rerank_models
            download_vllm_models
            ;;
        --vllm)
            download_vllm_models
            ;;
        --embedding)
            download_embedding_models
            ;;
        --rerank)
            download_rerank_models
            ;;
        --ollama)
            download_ollama_models
            ;;
        *)
            echo "用法: $0 [--all|--vllm|--embedding|--rerank|--ollama]"
            exit 1
            ;;
    esac

    echo ""
    echo "══════════════════════════════════════════════════════════════"
    log_ok "模型下载完成！"
    echo ""
    echo "  目录结构："
    echo "    $MODELS_DIR/"
    echo "    ├── inference/     ← vLLM 推理模型"
    echo "    ├── embedding/     ← BGE-M3 嵌入模型"
    echo "    └── rerank/        ← BGE-Reranker 重排模型"
    echo "══════════════════════════════════════════════════════════════"
}

main "$@"
