# vLLM / Ollama API Gateway —— 轻量路由网关
FROM python:3.11-slim

WORKDIR /gateway

# 安装依赖（版本锁定在 requirements.txt，与 app-server 一致）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制网关代码
COPY gateway.py .

# SECURITY: gateway.yaml 包含明文路由 key（ak_pool_*），不烘焙进镜像层。
# 通过 docker-compose.yaml 的 bind mount 在运行时以只读方式挂载，
# 防止 key 随镜像分发（docker push / docker save）泄露。
# 若恢复 COPY，请先评估镜像是否会上传公共/共享仓库。

EXPOSE 8080

CMD ["uvicorn", "gateway:app", "--host", "0.0.0.0", "--port", "8080"]
