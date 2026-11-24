# 共享模型配置

`model-config` 是一个独立的 Python 配置库，对外导入名为 `model_config`。
调用方只提供模型名，通过公开接口获得只读配置，不需要了解 YAML 文件位置、分组或校验逻辑。

## 公开接口

app-server、gateway 和模型启动适配器使用同一个接口：

```python
from model_config import get_model_config

inference = get_model_config("qwen2.5-1.8B-instruct")
print(inference.max_model_len)  # 4096

embedding = get_model_config("BAAI/bge-m3")
print(embedding.max_model_len)  # 8192
print(embedding.dimension)      # 1024
```

返回 `ModelConfig`，公开字段为 `name`、`model_type`、`max_model_len`、`dimension`。
配置对象只读；非 embedding 模型的 `dimension` 默认是 `None`。
查询会延迟加载并校验配置，每个进程缓存一份；模型名不存在、重复或配置无效时抛出公开的 `ModelConfigError`。
YAML 内部的 `max-model-len` 自动映射到 Python 属性 `max_model_len`。

本地开发只需在项目根目录安装一次（编辑模式）：

```bash
python -m pip install -e ./model-config
```

包构建会包含 `models.yaml`，不依赖调用方当前目录。
Docker 模式下 app-server、model-gateway 继承本模块的 `model-library` 模板，
共享只读库目录并获得导入路径，不需要在各自 Dockerfile 中复制模块内部文件。
目前这两个服务已可导入此库；既有业务配置加载器尚未迁移，原有窗口和预算配置仍按原逻辑读取。

`models.yaml` 按模型类型集中存放窗口、向量维度等参数。模型键与现有接口模型名完全一致，包括大小写。

## 启动

在项目根目录执行正常的 Compose 命令：

```bash
docker compose up -d --build
```

本模块是文件和共享启动模板，不创建独立的配置容器，不需要其他服务等待它启动。
本目录的 `docker-compose.yaml` 提供通用的 `model-library` 模板，仅供各服务通过 `extends` 继承，
不由根 Compose 直接 `include`，不会作为独立容器启动。
模型侧的 `vllm-base` 继承 `docker-runtime.yaml` 中的 `model-runtime` 模板；
该模板进一步继承配置库模板，并运行 `python3 -m model_config.runtime`。
库挂载路径、导入路径与模型启动适配细节全部集中在本模块维护。

每个 vLLM 容器通过该模板挂载相同的只读配置库。
适配器调用公开的 `get_model_config()` 获取配置，将 `--max-model-len` 的显式引用替换为数值，然后执行镜像原有的 `vllm serve`。
生成模型按 `--served-model-name` 查表；embedding 未单独配置服务名时按 `--model` 查表。
入口按完整模型 key 自动在 `inference`、`embedding` 分组中查找，不需要额外指定分组环境变量。
模型 key 在这两个分组中必须唯一；找不到模型或 key 存在歧义时会报错，不启动模型进程。
启动日志会显示匹配的模型和窗口，不打印完整启动参数或密钥。

Compose 中保留参数行，直接显示引用的模型 key，例如：

```yaml
--max-model-len BAAI/bge-m3:max-model-len
```

`<模型 key>:max-model-len` 是本项目共享入口定义的引用格式，非 Docker 或 vLLM 的原生语法。
入口检查引用 key 与实际模型名一致，将其替换为 `8192` 等数值后才交给 vLLM；数值只在 `models.yaml` 中维护。
无需宿主机 Python 启动脚本或窗口环境变量。
app-server 的内部窗口和业务预算目前尚未接入，网关仍按现有路由转发。

```bash
# 仅验证 Compose 编排结构，不运行 YAML 参数校验或启动模型
docker compose config --quiet

# 查看窗口读取日志
docker compose logs vllm-embedding

# 停止整个项目
docker compose down
```

修改 `models.yaml` 后，执行 `docker compose up -d --force-recreate`，让模型容器重新读取并校验配置。
这会重建服务容器；正在运行的模型不会热更新窗口。
模型容器每次启动都会先读取并校验配置，失败则不执行 vLLM。
配置错误只阻止对应模型进程加载，不再阻塞 app-server 或 model-gateway 的启动。

## 配置结构

```yaml
inference:
  qwen2.5-1.8B-instruct:
    max-model-len: 4096

embedding:
  BAAI/bge-m3:
    max-model-len: 8192
    dimension: 1024
```

生成模型的窗口包含输入与输出；embedding 窗口用于输入，`dimension` 为输出向量维度。
`max-model-len`、`dimension` 必须为正整数。
摘要和护栏使用的生成模型同属 `inference`；当前只登记已有配置中的三个生成模型和一个 embedding 模型。
路径、密钥、显存比例、超时等仍由各服务配置维护。

当前窗口值取自初始部署配置，尚未核实为模型官方能力上限；后续需要区分模型能力和业务窗口。
Embedding 的 `8192` 为窗口记录，原服务端 `8182` 包含安全预留。

开发验证（开发环境需已有 PyYAML）：

```bash
python -m unittest discover -s model-config/tests -v
```
