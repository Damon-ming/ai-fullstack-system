# 基础镜像：以官方python3.11 slim轻量镜像作为基底
FROM python:3.11-slim

WORKDIR /app-server

# 安装系统依赖
# `-y`：自动回答 yes，安装交互的时候不用人工确认
# `--no-install-recommends`：**不安装推荐的附属软件包**
# `build‑essential`：Debian 的软件包集合，里面包含 `gcc/g++` 编译器、make 工具。
# 作用：有些 Python 库（比如 numpy、pandas、pyarrow、某些向量库）需要本地 C 语言编译，就必须要有 gcc。
# 删除 apt 下载的软件源缓存文件。
# `apt update` 会下载一大堆索引缓存，占用镜像空间，构建完立刻删掉，**减少最终镜像大小**。
RUN apt update && apt install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 复制项目依赖
COPY requirements.txt .

# 1. `--no‑cache-dir` 不保存 pip 下载的缓存包**。
# `.whl` 是 Python 的**轮子包（wheel）**文件后缀
RUN pip install --no-cache-dir -r requirements.txt

# 复制全部业务代码
COPY . .

# ── 构建时注入 ─────────────────────────────────────────────────────
# SERVER_BUILD_ENV 构建参数（运行时不可变）：
#   0 → 锁定 release，忽略 APP_ENV（生产流水线，不可切换）
#   1 → 默认 debug，APP_ENV 可覆盖（开发/预发流水线，可切换）
ARG SERVER_BUILD_ENV=0
RUN printf 'SERVER_BUILD_ENV = %s\n' "$SERVER_BUILD_ENV" > src/com/damon/ming/debug/build_info.py

# 容器内部访问ollama地址：http://ollama-server:11434
# ENV OLLAMA_BASE_URL=http://ollama-server:11434

# 启动入口，根据你项目实际启动文件修改
# CMD ["python3", "-m", "src.com.damon.ming.main"]
