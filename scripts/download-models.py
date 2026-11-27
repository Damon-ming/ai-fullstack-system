# scripts/download-models.py
"""
scripts/download-models.py —— 一键下载所有 AI 模型（Python 版，支持 Windows/Linux/macOS）

用法：
    python scripts/download-models.py                # 下载全部
    python scripts/download-models.py --vllm         # 仅 vLLM 推理模型
    python scripts/download-models.py --embedding    # 仅 Embedding 模型
    python scripts/download-models.py --rerank       # 仅 Rerank 模型

环境变量：
    MODELS_DIR    模型根目录（可选覆盖，默认读取项目根目录 .env 的 DATA_DIR/models）
    DATA_DIR      宿主机数据根目录；未导出时从项目根目录 .env 读取
    HF_ENDPOINT   镜像站（默认 https://hf-mirror.com）
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

# ── 模型清单 ──────────────────────────────────────────────────────
# 格式: (HuggingFace repo_id, 本地子目录, 描述)

# 与 model-gateway/config/docker/docker-vllm-inference.yaml 保持一致。
VLLM_MODELS = [
    (
        "Qwen/Qwen2.5-1.5B-Instruct",
        "inference/Qwen2.5-1.5B-Instruct",
        "主推理模型 (1.5B)",
    ),
    (
        "Qwen/Qwen2.5-0.5B-Instruct",
        "inference/Qwen2.5-0.5B-Instruct",
        "摘要模型 (0.5B)",
    ),
    ("Qwen/Qwen3Guard-Gen-0.6B", "inference/Qwen3Guard-Gen-0.6B", "护栏模型 (0.6B)"),
]

# embedding 写入 Hub 缓存目录，供容器中的 model ID 与 tokenizer 复用。
EMBEDDING_MODELS = [
    ("BAAI/bge-m3", "embedding", "BGE-M3 多语言嵌入"),
]

RERANK_MODELS = [
    (
        "BAAI/bge-reranker-v2-m3",
        "rerank/bge-reranker-v2-m3",
        "BGE-Reranker v2 M3（中英文重排）",
    ),
]


# ── 工具函数 ──────────────────────────────────────────────────────


def get_models_dir() -> Path:
    """获取宿主机模型目录，默认与 Compose 的 DATA_DIR/models 挂载源一致。"""
    models_dir = os.environ.get("MODELS_DIR")
    if models_dir and models_dir.strip():
        return Path(models_dir).expanduser()

    data_dir = os.environ.get("DATA_DIR") or _read_project_env("DATA_DIR")
    if not data_dir:
        raise ValueError(
            "未找到 DATA_DIR。请在项目根目录 .env 中配置 DATA_DIR，"
            "或设置 MODELS_DIR 覆盖模型下载目录。"
        )

    path = Path(data_dir).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    return path / "models"


def _read_project_env(name: str) -> str | None:
    """读取项目根目录 .env 中的简单 KEY=VALUE 配置。"""
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.is_file():
        return None

    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() != name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        return value or None
    return None


def get_hf_endpoint() -> str:
    return os.environ.get("HF_ENDPOINT", "https://hf-mirror.com")


def download_hf_model(
    repo_id: str, local_subdir: str, desc: str, models_dir: Path, *, cache: bool = False
) -> bool:
    """下载或恢复模型；embedding 使用 Hub 缓存，其他模型使用固定目录。"""
    target = models_dir / local_subdir
    print(f"  [下载] {desc}\n        repo: {repo_id}\n        dest: {target}")
    try:
        from huggingface_hub import snapshot_download

        options = {"cache_dir" if cache else "local_dir": str(target)}
        snapshot_download(repo_id=repo_id, endpoint=get_hf_endpoint(), **options)
        print(f"  [完成] {desc}")
        return True
    except ImportError:
        print("  [失败] 请先安装依赖：python -m pip install huggingface-hub")
        return False
    except Exception as exc:
        print(f"  [失败] {desc}: {exc}")
        return False


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
    parser.add_argument("--all", action="store_true", help="下载所有模型")
    parser.add_argument("--vllm", action="store_true", help="仅下载 vLLM 推理模型")
    parser.add_argument(
        "--embedding", action="store_true", help="仅下载 Embedding 模型"
    )
    parser.add_argument("--rerank", action="store_true", help="仅下载 Rerank 模型")
    parser.add_argument("--models-dir", type=str, help="自定义模型根目录")
    args = parser.parse_args()

    models_dir = Path(args.models_dir) if args.models_dir else get_models_dir()

    # 如果没有任何 --xxx 标记，下载全部
    no_filter = args.all or not (args.vllm or args.embedding or args.rerank)

    print("=" * 60)
    print("  AI Fullstack System —— 模型一键下载")
    print(f"  模型目录: {models_dir}")
    print(f"  HF 镜像:  {get_hf_endpoint()}")
    print("=" * 60)

    # 创建目录
    for subdir in ["inference", "embedding", "rerank"]:
        (models_dir / subdir).mkdir(parents=True, exist_ok=True)

    print_disk_space(models_dir)

    results = {"success": 0, "fail": 0}

    # 定义下载器
    def _download(repo, subdir, desc, *, cache=False):
        r = download_hf_model(repo, subdir, desc, models_dir, cache=cache)
        results["success" if r else "fail"] += 1

    if no_filter or args.embedding:
        download_category(
            "Embedding 模型",
            EMBEDDING_MODELS,
            lambda *args: _download(*args, cache=True),
        )
    if no_filter or args.rerank:
        download_category("Rerank 模型", RERANK_MODELS, _download)
    if no_filter or args.vllm:
        download_category("vLLM 推理模型", VLLM_MODELS, _download)
    print(f"\n{'=' * 60}")
    print(f"  下载完毕 —— 成功: {results['success']}  失败: {results['fail']}")
    print(f"{'=' * 60}")
    return 1 if results["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
