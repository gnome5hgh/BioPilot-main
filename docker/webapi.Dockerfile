# BioPilot 引擎适配层（多用户模式）：pip 装包 + 运行时挂载配置/工作区/插件。
# 信任边界：只监听容器内网（compose 网络即内网边界），绝不映射宿主公网端口。
FROM python:3.11-slim

# 同 paper-search-mcp.Dockerfile：apt 与 PyPI 默认走阿里云镜像，换源用构建参数覆盖。
# APT_MIRROR 只写主机名；用 http 的 PyPI 镜像才需要 PIP_TRUSTED_HOST。
ARG APT_MIRROR=mirrors.aliyun.com
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_TRUSTED_HOST=

WORKDIR /app
# 只替换主机名，debian 与 debian-security 两个源共用它；兼容 deb822 与老式 list。
RUN if [ -n "$APT_MIRROR" ]; then \
      for f in /etc/apt/sources.list /etc/apt/sources.list.d/*.sources /etc/apt/sources.list.d/*.list; do \
        if [ -f "$f" ]; then sed -i "s|deb.debian.org|$APT_MIRROR|g" "$f"; fi; \
      done; \
    fi \
    && apt-get update && apt-get install -y --no-install-recommends gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# 写成 pip 配置文件，让依赖自身的构建隔离环境（PEP 517）也走同一个索引。
RUN pip config set global.index-url "$PIP_INDEX_URL" \
    && if [ -n "$PIP_TRUSTED_HOST" ]; then pip config set global.trusted-host "$PIP_TRUSTED_HOST"; fi

COPY pyproject.toml README.md ./
COPY biopilot ./biopilot
RUN pip install --no-cache-dir .

# agents 插件、config.yaml、.biopilot 工作区（skills/intent/镜像语料/运行数据）
# 由部署时挂载：compose 里见 volumes。
EXPOSE 8300
CMD ["python", "-m", "biopilot"]
