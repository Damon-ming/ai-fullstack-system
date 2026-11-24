"""容器内校验模型配置，并在加载模型前解析显式的模型参数引用。"""

import os
import sys

from . import get_model_config


def model_argument(args: list[str]) -> str:
    flag = "--served-model-name" if "--served-model-name" in args else "--model"
    if args.count(flag) != 1:
        raise ValueError(f"必须配置且只配置一个 {flag}")
    index = args.index(flag)
    if index + 1 >= len(args) or args[index + 1].startswith("--"):
        raise ValueError(f"{flag} 缺少模型名")
    return args[index + 1]


def resolve_window(args: list[str]) -> tuple[str, int]:
    name = model_argument(args)
    config = get_model_config(name)
    expected = f"{name}:max-model-len"
    if args.count("--max-model-len") != 1 or any(
        arg.startswith("--max-model-len=") for arg in args
    ):
        raise ValueError(f"--max-model-len 必须引用 {expected}")
    index = args.index("--max-model-len")
    if index + 1 >= len(args) or args[index + 1] != expected:
        raise ValueError(f"--max-model-len 必须引用 {expected}，并与实际模型名一致")
    return config.name, config.max_model_len


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        name, window = resolve_window(args)
        print(f"[model-config] model={name} --max-model-len {window}", flush=True)
        resolved_args = list(args)
        resolved_args[resolved_args.index("--max-model-len") + 1] = str(window)
        # 仅替换窗口引用，保留其余参数；exec 保留 Docker 的信号传递与退出码。
        os.execvp("vllm", ["vllm", "serve", *resolved_args])
    except (OSError, TypeError, ValueError) as exc:
        print(f"[model-config] 配置加载失败: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
