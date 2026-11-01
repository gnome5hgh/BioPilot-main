# BioPilot 引擎适配层（多用户模式）：pip 装包 + 运行时挂载配置/工作区/插件。
# 信任边界：只监听容器内网（compose 网络即内网边界），绝不映射宿主公网端口。
FROM python:3.11-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY biopilot ./biopilot
RUN pip install --no-cache-dir .

# agents 插件、config.yaml、.biopilot 工作区（skills/intent/镜像语料/运行数据）
# 由部署时挂载：compose 里见 volumes。
EXPOSE 8300
CMD ["python", "-m", "biopilot", "--web"]
