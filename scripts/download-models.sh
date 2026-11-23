#!/usr/bin/env bash
# 模型清单和下载逻辑统一由 Python 脚本维护。
# 用法: bash scripts/download-models.sh [--all|--vllm|--embedding|--rerank]
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if command -v python3 >/dev/null 2>&1; then
    exec python3 "$SCRIPT_DIR/download-models.py" "$@"
elif command -v python >/dev/null 2>&1; then
    exec python "$SCRIPT_DIR/download-models.py" "$@"
else
    printf '%s\n' '请先安装 Python 和 huggingface-hub。' >&2
    exit 1
fi
