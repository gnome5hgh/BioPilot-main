# 文献检索 MCP server（paper-search-mcp）：以 streamable-http 暴露给 SpringBoot 的
# MCP 客户端。只应在 compose 内网使用；如需本机调试，compose 仅把端口映射到回环。
FROM python:3.11-slim

WORKDIR /app
# paper-search-mcp 仍依赖 mcp 1.x（2.x 改了 FastMCP 导入路径）
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "mcp<2" \
    "git+https://github.com/openags/paper-search-mcp@cab1b5cc276a0cd004a0044003926a6440088049"

EXPOSE 8000
CMD ["python", "-m", "paper_search_mcp.server", \
     "--transport", "streamable-http", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--path", "/mcp"]
