# vLLM / Ollama API Gateway —— 轻量路由网关
FROM python:3.11-slim

WORKDIR /gateway

# 安装依赖
RUN pip install --no-cache-dir fastapi uvicorn httpx pyyaml

# 复制网关代码 + 配置（gateway.yaml 烘焙进镜像，运行时不可变）
COPY gateway.py .
COPY config/gateway.yaml /etc/gateway/gateway.yaml

EXPOSE 8080

CMD ["uvicorn", "gateway:app", "--host", "0.0.0.0", "--port", "8080"]
