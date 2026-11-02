-- 文献检索 MCP server 配置表：已有库一次性补齐（幂等）。
-- 新建库由 server/script/sql/biopilot.sql 与 docker/mysql-init 直接建表。

CREATE TABLE IF NOT EXISTS bio_literature_mcp_server (
    id                  VARCHAR(64)  NOT NULL COMMENT '配置ID',
    name                VARCHAR(64)  NOT NULL COMMENT 'server 名（唯一）',
    transport           VARCHAR(16)  NOT NULL DEFAULT 'http' COMMENT 'http/stdio',
    url                 VARCHAR(500) NULL COMMENT 'http 端点',
    command             VARCHAR(200) NULL COMMENT 'stdio 可执行文件',
    args_json           TEXT         NULL COMMENT 'stdio 参数 JSON 数组',
    env_json            TEXT         NULL COMMENT 'stdio 环境变量 JSON（密钥）',
    headers_json        TEXT         NULL COMMENT 'http 请求头 JSON（密钥）',
    adapter             VARCHAR(32)  NOT NULL DEFAULT 'paper_search' COMMENT '业务适配器',
    allowed_tools_json  TEXT         NULL COMMENT '工具白名单 JSON 数组',
    disabled_tools_json TEXT         NULL COMMENT '工具黑名单 JSON 数组',
    enabled             TINYINT      NOT NULL DEFAULT 1 COMMENT '是否启用',
    connect_timeout_ms  INT          NOT NULL DEFAULT 30000 COMMENT '建连超时',
    call_timeout_ms     INT          NOT NULL DEFAULT 60000 COMMENT '调用超时',
    created_at          VARCHAR(40)  NOT NULL COMMENT '创建时间',
    updated_at          VARCHAR(40)  NOT NULL COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_literature_mcp_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文献检索 MCP server 配置';
