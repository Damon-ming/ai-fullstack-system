"""从唯一模型配置源生成根目录 model-config.env，在运行 Compose 前执行。"""

import argparse
import math
import os
from pathlib import Path
import re
import sys
import tempfile

if __package__:
    from ._catalog import ModelConfigError, _read_model_values
else:
    from _catalog import ModelConfigError, _read_model_values


MODULE_DIR = Path(__file__).resolve().parent


def identifier(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").upper()
    if not name or name[0].isdigit():
        raise ModelConfigError(f"无法生成合法的环境变量名: {value!r}")
    return name


def render_env(path: Path) -> str:
    models = _read_model_values(path)
    variables = {}
    for group in ("inference", "embedding"):
        for model_name, values in models[group].items():
            # BAAI/bge-m3 -> BGE_M3；模型名中的版本、小数点等转为下划线。
            prefix = identifier(model_name.rsplit("/", 1)[-1])
            for field, value in values.items():
                if not isinstance(field, str):
                    raise ModelConfigError(f"{model_name} 的参数名必须是字符串")
                variable = f"{prefix}_{identifier(field)}"
                if variable in variables:
                    raise ModelConfigError(f"环境变量名冲突: {variable}")
                if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
                    raise ModelConfigError(f"{model_name}.{field} 只能导出有限数值参数")
                variables[variable] = str(value)
    lines = ["# Generated from model-config/models.yaml; do not edit manually."]
    lines.extend(f"{key}={value}" for key, value in variables.items())
    return "\n".join(lines) + "\n"


def export_env(source: Path, destination: Path) -> None:
    content = render_env(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=destination.parent,
            prefix=destination.name + ".", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", type=Path, default=MODULE_DIR / "models.yaml")
    parser.add_argument("--output", type=Path, default=MODULE_DIR.parent / "model-config.env")
    args = parser.parse_args(argv)
    try:
        export_env(args.models, args.output)
    except (OSError, ModelConfigError) as exc:
        print(f"模型环境配置生成失败: {exc}", file=sys.stderr)
        return 1
    print(f"已生成模型环境配置: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
