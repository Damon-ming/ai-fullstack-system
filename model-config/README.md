# 共享模型配置

`models.yaml` 是文本推理模型服务窗口的维护源。`export_env.py` 校验后将它导出为项目根目录的 `model-config.env`。
生成文件仅作为部署产物，不手动编辑，已加入 Git 忽略规则。

## 使用

```bash
# 首次安装配置模块及依赖
python -m pip install -e ./model-config

# 首次使用或每次修改 models.yaml 后，生成根目录环境文件
python model-config/export_env.py

# 仍使用普通 Compose 命令，不需要 --env-file 参数
docker compose up -d --build
```

导出必须在 Compose 解析服务配置之前完成；本模块不作为配置容器启动，不修改 vLLM 的 entrypoint。
导出会先校验全部数据，再原子替换生成文件，失败时保留原有文件并返回非零退出码。
修改 YAML 后要重新导出，再执行 `docker compose up -d`；已经运行的进程不会热更新配置。

## Docker Compose 的两种读取

根 Compose 保持 `include` 结构，通过 `include.env_file: ./model-config.env` 替换子文件中的 `${变量}`：

```yaml
--max-model-len ${QWEN2_5_1_8B_INSTRUCT_MAX_MODEL_LEN}
```

app-server 和 model-gateway 各自服务下的 `env_file: ../model-config.env` 将同一份变量注入容器。
两处用途不同：`include.env_file` 解析 Compose 参数，服务 `env_file` 提供容器内环境变量。
根目录不重新定义服务，不为此增加 `extends` 或 YAML 锚点。
项目根目录 `.env` 仍按 Compose 默认机制提供部署路径、数据库和密钥等配置。
模型变量只在生成文件中维护，避免在宿主机环境或根 `.env` 重复设置同名变量而覆盖生成值。

app-server 从此文件读取推理模型窗口；RAG embedding 的输入上限、维度和运行窗口由
`app/config/ai/rag/rag-runtime.yaml` 单独维护。vLLM embedding 服务的部署窗口在
`model-gateway/config/docker/docker-vllm-embedding.yaml` 配置：

```python
import os

max_model_len = int(os.environ["QWEN2_5_1_8B_INSTRUCT_MAX_MODEL_LEN"])
```

应用自己的 YAML 中 `${变量}` 不会因 env_file 自动展开，仍需要配置加载器支持。

## 命名和扩展

```yaml
inference:
  qwen2.5-1.8B-instruct:
    max-model-len: 4096
```

导出为：

```dotenv
QWEN2_5_1_8B_INSTRUCT_MAX_MODEL_LEN=4096
```

变量前缀使用模型 key 最后一个 `/` 后的名称，非字母数字转换为下划线并转大写。
字段名采用相同规则。规范化后若变量重名则报错，避免不同模型静默覆盖。
当前支持有限数值参数；新增如 `gpu-memory-utilization: 0.4` 会自动导出对应变量，无需修改导出器。
新增变量不会自动接入业务：使用方仍需在自己的配置中引用它。
`max-model-len` 必须为正整数。
当前窗口来自已有部署值，尚未核实为模型官方最大能力。

现有 `get_model_config()` Python 查询接口保留供安装库后的代码使用；本次 Docker 部署通过 env 文件共享数值，
不依赖旧的共享库挂载或自定义模型启动适配模板。

## 验证

```bash
python -m unittest discover -s model-config/tests -v
docker compose config --quiet
```
