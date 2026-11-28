# model-gateway/export_model_env.py
"""把 models.yaml 导出为 Docker Compose 可插值的模块环境文件。"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml

MODULE_DIR = Path(__file__).resolve().parent
MODELS_PATH = MODULE_DIR / "config" / "models.yaml"
OUTPUT_PATH = MODULE_DIR / "model-gateway-models.env"


def _variable_name(model_name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", model_name).strip("_").upper()
    if not normalized or normalized[0].isdigit():
        raise ValueError(f"无法为模型名生成环境变量名: {model_name!r}")
    return f"{normalized}_MAX_MODEL_LEN"


def _render_env() -> str:
    raw: Any = yaml.safe_load(MODELS_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("models"), dict):
        raise TypeError("models.yaml 必须包含 models 映射")
    models = raw["models"]
    if not models:
        raise ValueError("models.yaml 的 models 不能为空")

    values: dict[str, int] = {}
    for model_name, config in models.items():
        if not isinstance(model_name, str) or not model_name.strip():
            raise ValueError("模型名称必须是非空字符串")
        if not isinstance(config, dict):
            raise TypeError(f"models.{model_name} 必须是映射")
        max_model_len = config.get("max_model_len")
        if type(max_model_len) is not int or max_model_len < 2:
            raise ValueError(
                f"models.{model_name}.max_model_len 必须是大于等于 2 的整数"
            )
        variable = _variable_name(model_name)
        if variable in values:
            raise ValueError(f"环境变量名称冲突: {variable}")
        values[variable] = max_model_len

    lines = ["# Generated from model-gateway/config/models.yaml; do not edit."]
    lines.extend(f"{name}={value}" for name, value in values.items())
    return "\n".join(lines) + "\n"


def main() -> None:
    content = _render_env()
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=OUTPUT_PATH.parent,
            prefix=f"{OUTPUT_PATH.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, OUTPUT_PATH)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    print(f"已生成 Docker Compose 模型参数: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
