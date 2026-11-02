# 文献检索 MCP server（paper-search-mcp）：以 streamable-http 暴露给 SpringBoot 的
# MCP 客户端。只应在 compose 内网使用；如需本机调试，compose 仅把端口映射到回环。
FROM python:3.11-slim

# apt 与 PyPI 默认走阿里云镜像：直连官方源在国内常见几十 kB/s，一次构建要卡半小时以上。
# 换源用构建参数覆盖（compose 会把同名环境变量透传进来）；APT_MIRROR 只写主机名。
# 用 http 的 PyPI 镜像才需要 PIP_TRUSTED_HOST。
ARG APT_MIRROR=mirrors.aliyun.com
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG PIP_TRUSTED_HOST=

WORKDIR /app
# 只替换主机名：debian 与 debian-security 两个源共用 deb.debian.org 主机，一次替换全覆盖；
# 同时兼容 deb822（*.sources）与老式（*.list）两种写法。
RUN if [ -n "$APT_MIRROR" ]; then \
      for f in /etc/apt/sources.list /etc/apt/sources.list.d/*.sources /etc/apt/sources.list.d/*.list; do \
        if [ -f "$f" ]; then sed -i "s|deb.debian.org|$APT_MIRROR|g" "$f"; fi; \
      done; \
    fi \
    && apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# 写成 pip 配置文件而不是给每条命令加 --index-url：依赖自身的构建隔离环境
# （PEP 517）里的 pip 调用也读同一份配置，不会漏掉其中一次。
RUN pip config set global.index-url "$PIP_INDEX_URL" \
    && if [ -n "$PIP_TRUSTED_HOST" ]; then pip config set global.trusted-host "$PIP_TRUSTED_HOST"; fi

# 用 commit 归档包而不是 git+https：容器网络里 GitHub 的 git 传输常被 TLS 中断
# （GnuTLS recv error -110，且 pip 对 VCS 克隆不做重试）；归档包走普通 HTTPS，
# 失败可重试，URL 里的 commit 哈希也保证装的就是钉住的那一版。
RUN pip install --no-cache-dir "mcp<2" \
    "https://codeload.github.com/openags/paper-search-mcp/tar.gz/cab1b5cc276a0cd004a0044003926a6440088049"

EXPOSE 8000
CMD ["python", "-m", "paper_search_mcp.server", \
     "--transport", "streamable-http", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--path", "/mcp"]
