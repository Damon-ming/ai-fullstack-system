# scripts/download-models.py
"""
scripts/download-models.py —— 一键下载所有 AI 模型（Python 版，支持 Windows/Linux/macOS）

用法：
    python scripts/download-models.py                # 下载全部
    python scripts/download-models.py --vllm         # 仅 vLLM 推理模型
    python scripts/download-models.py --embedding    # 仅 Embedding 模型
    python scripts/download-models.py --rerank       # 仅 Rerank 模型

环境变量：
    MODELS_DIR    模型根目录（默认 /root/damon/models，Windows 自动检测为 C:\\models）
    HF_ENDPOINT   镜像站（默认 https://hf-mirror.com）
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ── 模型清单 ──────────────────────────────────────────────────────
# 格式: (HuggingFace repo_id, 本地子目录, 描述)

VLLM_MODELS = [
    ("Qwen/Qwen2.5-7B-Instruct", "inference/Qwen2.5-7B-Instruct", "聊天主模型 (7B)"),
    (
        "Qwen/Qwen2.5-0.5B-Instruct",
        "inference/Qwen2.5-0.5B-Instruct",
        "意图识别模型 (0.5B)",
    ),
    (
        "Qwen/Qwen2.5-1.8B-Instruct",
        "inference/Qwen2.5-1.8B-Instruct",
        "查询改写模型 (1.8B)",
    ),
    (
        "Qwen/Qwen2.5-1.5B-Instruct",
        "inference/Qwen2.5-1.5B-Instruct",
        "摘要模型 (1.5B)",
    ),
    ("Qwen/Qwen3Guard-Gen-4B", "inference/Qwen3Guard-Gen-4B", "护栏安全模型 (4B)"),
]

EMBEDDING_MODELS = [
    ("BAAI/bge-m3", "embedding/BAAI/bge-m3", "BGE-M3 多语言嵌入"),
]

RERANK_MODELS = [
    (
        "BAAI/bge-reranker-v2-gemma",
        "rerank/bge-reranker-v2-gemma",
        "BGE-Reranker v2 Gemma（中文主力）",
    ),
    (
        "BAAI/bge-reranker-v2-m3",
        "rerank/bge-reranker-v2-m3",
        "BGE-Reranker v2 M3（轻量/降级）",
    ),
]


# ── 工具函数 ──────────────────────────────────────────────────────


def get_models_dir() -> Path:
    """获取模型根目录。"""
    default = "/root/damon/models"
    if sys.platform == "win32":
        default = "C:\\models"
    return Path(os.environ.get("MODELS_DIR", default))


def get_hf_endpoint() -> str:
    return os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")


def dir_exists_and_nonempty(path: Path) -> bool:
    """检查目录存在且非空。"""
    return path.is_dir() and any(path.iterdir())


def download_hf_model(
    repo_id: str, local_subdir: str, desc: str, models_dir: Path
) -> bool:
    """通过 huggingface-cli 下载模型。"""
    local_path = models_dir / local_subdir

    if dir_exists_and_nonempty(local_path):
        print(f"  [SKIP] {desc}（已存在: {local_path}）")
        return True

    print(f"  [下载] {desc}")
    print(f"        repo: {repo_id}")
    print(f"        dest: {local_path}")

    local_path.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["HF_ENDPOINT"] = get_hf_endpoint()

    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "huggingface_hub",
                "download",
                repo_id,
                "--local-dir",
                str(local_path),
                "--local-dir-use-symlinks",
                "False",
                "--resume-download",
            ],
            env=env,
            check=True,
        )
        print(f"  [完成] {desc}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [失败] {desc}: {e}")
        return False
    except FileNotFoundError:
        # huggingface_hub 未安装，尝试 pip install
        print("  [安装] huggingface-hub 未安装，正在安装...")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "huggingface-hub"],
            check=True,
        )
        return download_hf_model(repo_id, local_subdir, desc, models_dir)


def print_disk_space(path: Path) -> None:
    """打印磁盘可用空间。"""
    try:
        if sys.platform != "win32":
            usage = shutil.disk_usage(str(path))
            avail_gb = usage.free / (1024**3)
            print(f"  可用空间: {avail_gb:.1f} GB")
        else:
            import ctypes

            free_bytes = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                str(path.root), None, None, ctypes.pointer(free_bytes)
            )
            print(f"  可用空间: {free_bytes.value / (1024**3):.1f} GB")
    except Exception:
        pass


# ── 下载任务 ──────────────────────────────────────────────────────


def download_category(title: str, models, download_fn) -> None:
    print(f"\n{'=' * 50}")
    print(f"  {title}")
    print(f"{'=' * 50}")
    for args in models:
        download_fn(*args)


def main():
    parser = argparse.ArgumentParser(description="AI Fullstack System 模型下载脚本")
    parser.add_argument("--vllm", action="store_true", help="仅下载 vLLM 推理模型")
    parser.add_argument(
        "--embedding", action="store_true", help="仅下载 Embedding 模型"
    )
    parser.add_argument("--rerank", action="store_true", help="仅下载 Rerank 模型")
    parser.add_argument("--models-dir", type=str, help="自定义模型根目录")
    args = parser.parse_args()

    models_dir = Path(args.models_dir) if args.models_dir else get_models_dir()

    # 如果没有任何 --xxx 标记，下载全部
    no_filter = not (args.vllm or args.embedding or args.rerank)

    print("=" * 60)
    print("  AI Fullstack System —— 模型一键下载")
    print(f"  模型目录: {models_dir}")
    print(f"  HF 镜像:  {get_hf_endpoint()}")
    print("=" * 60)

    # 创建目录
    for subdir in ["inference", "embedding", "rerank"]:
        (models_dir / subdir).mkdir(parents=True, exist_ok=True)

    print_disk_space(models_dir)

    results = {"success": 0, "skip": 0, "fail": 0}

    # 定义下载器
    def _dl_vllm(repo, subdir, desc):
        r = download_hf_model(repo, subdir, desc, models_dir)
        results["success" if r else "fail"] += 1

    if no_filter or args.embedding:
        download_category("Embedding 模型", EMBEDDING_MODELS, _dl_vllm)
    if no_filter or args.rerank:
        download_category("Rerank 模型", RERANK_MODELS, _dl_vllm)
    if no_filter or args.vllm:
        download_category("vLLM 推理模型", VLLM_MODELS, _dl_vllm)
    print(f"\n{'=' * 60}")
    print(f"  下载完毕 —— 成功: {results['success']}  失败: {results['fail']}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
