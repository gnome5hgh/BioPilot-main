CREATE DATABASE IF NOT EXISTS biopilot_test;
-- 测试库也需要 sys_* 表：Java 测试（AuthFlowTest）连 biopilot_test 并 TRUNCATE
USE biopilot_test;
CREATE TABLE IF NOT EXISTS sys_user (
    user_id     BIGINT       NOT NULL AUTO_INCREMENT COMMENT '用户ID（全局隔离键）',
    user_name   VARCHAR(64)  NOT NULL                COMMENT '登录用户名',
    password    VARCHAR(100) NOT NULL                COMMENT 'BCrypt 摘要',
    nick_name   VARCHAR(64)  NULL                    COMMENT '显示名',
    role        VARCHAR(20)  NOT NULL DEFAULT 'USER' COMMENT '角色键（ADMIN/USER 两档）',
    status      CHAR(1)      NOT NULL DEFAULT '0'    COMMENT '状态（0正常 1停用）',
    create_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id),
    UNIQUE KEY uk_sys_user_name (user_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户信息表';
CREATE TABLE IF NOT EXISTS sys_login_log (
    id          BIGINT      NOT NULL AUTO_INCREMENT COMMENT '日志ID',
    user_name   VARCHAR(64) NULL COMMENT '尝试登录的用户名',
    user_id     BIGINT      NULL COMMENT '关联用户（未知为 NULL）',
    outcome     VARCHAR(10) NOT NULL COMMENT 'success/failed',
    ip          VARCHAR(64) NULL COMMENT '来源 IP',
    create_time DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_login_log_user (user_id, create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='登录日志表';
-- 项目表：与 server/script/sql/biopilot.sql 等价；测试库也建一份，避免项目域用例缺表
CREATE TABLE IF NOT EXISTS bio_project (
    project_id    VARCHAR(64)  NOT NULL COMMENT '项目ID',
    user_id       VARCHAR(191) NOT NULL COMMENT '归属用户（租户列）',
    name          VARCHAR(50)  NOT NULL COMMENT '项目名称',
    billing_group VARCHAR(64)  NULL COMMENT '计费组（原型字段，保留无逻辑）',
    description   VARCHAR(100) NULL COMMENT '简介',
    create_time   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id),
    KEY idx_project_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目表';
-- 定时任务表：与 server/script/sql/biopilot.sql 等价；测试库也建一份，避免调度用例缺表
CREATE TABLE IF NOT EXISTS bio_schedule_task (
    id               VARCHAR(64)  NOT NULL COMMENT '任务ID',
    user_id          VARCHAR(191) NOT NULL COMMENT '归属用户（租户列）',
    conversation_id  VARCHAR(64)  NOT NULL COMMENT '归属会话',
    name             VARCHAR(200) NOT NULL COMMENT '任务名',
    task             TEXT         NOT NULL COMMENT '到点执行的任务文本',
    interval_minutes INTEGER      NOT NULL COMMENT '执行周期（分钟）',
    paused           INTEGER      NOT NULL DEFAULT 0 COMMENT '1=暂停',
    last_run_at      VARCHAR(40)  NULL COMMENT '上次执行时间（引擎回写）',
    next_run_at      VARCHAR(40)  NOT NULL COMMENT '下次执行时间（引擎回写）',
    created_at       VARCHAR(40)  NOT NULL COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_sched_user (user_id),
    KEY idx_sched_next (next_run_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='定时任务表';
-- 平台文件表：测试库也建一份，避免 Java/Python 用例缺表
-- 与 server/script/sql/biopilot.sql、docker/mysql-init/08-catalog-tables.sql 等价
CREATE TABLE IF NOT EXISTS bio_file (
    id              VARCHAR(64)  NOT NULL COMMENT '文件ID（论文/数据/文档/产物共用）',
    user_id         VARCHAR(191) NOT NULL COMMENT '归属用户（租户列）',
    kind            VARCHAR(16)  NOT NULL COMMENT '类型（paper/data/document/artifact）',
    name            VARCHAR(255) NOT NULL COMMENT '展示名',
    name_key        VARCHAR(255) COLLATE utf8mb4_0900_bin NULL
                    COMMENT '归一化名（NFC+trim+lower）；artifact 为 NULL（不占名）',
    oss_key         VARCHAR(500) NOT NULL COMMENT '当前对象键',
    size_bytes      BIGINT       NOT NULL DEFAULT 0 COMMENT '字节数',
    content_type    VARCHAR(120) NULL COMMENT 'MIME',
    sha256          CHAR(64)     NULL COMMENT '内容摘要',
    version         BIGINT       NOT NULL DEFAULT 1 COMMENT '内容版本（文档更新用）',
    source          VARCHAR(16)  NULL COMMENT '来源（upload/artifact/paper/document/agent/import）',
    run_id          VARCHAR(64)  NULL COMMENT '分析产物所属 run',
    conversation_id VARCHAR(64)  NULL COMMENT '所属会话',
    title           VARCHAR(500) NULL COMMENT '论文标题（Java 提取；宁空勿错）',
    authors         VARCHAR(1000) NULL COMMENT '论文作者',
    year            VARCHAR(10)  NULL COMMENT '论文年份',
    journal         VARCHAR(300) NULL COMMENT '论文期刊/会议',
    kb_enabled      TINYINT      NULL COMMENT '是否加入知识库（仅 paper；索引状态在引擎的 bio_rag_paper_status）',
    citation_id     VARCHAR(64)  NULL COMMENT '引用库行 id（仅 paper）',
    created_at      VARCHAR(40)  NOT NULL COMMENT '创建时间',
    updated_at      VARCHAR(40)  NULL COMMENT '更新时间',
    seq             BIGINT       NOT NULL AUTO_INCREMENT,
    PRIMARY KEY (id),
    UNIQUE KEY uk_file_seq (seq),
    UNIQUE KEY uk_file_name (user_id, name_key),
    KEY idx_file_user_kind (user_id, kind, seq),
    KEY idx_file_run (user_id, run_id),
    KEY idx_file_kb (user_id, kind, kb_enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='统一文件表';
-- 文献检索 MCP 配置表：测试库也建一份，避免服务启动时缺表
CREATE TABLE IF NOT EXISTS bio_literature_mcp_server (
    id                  VARCHAR(64)  NOT NULL,
    name                VARCHAR(64)  NOT NULL,
    transport           VARCHAR(16)  NOT NULL DEFAULT 'http',
    url                 VARCHAR(500) NULL,
    command             VARCHAR(200) NULL,
    args_json           TEXT         NULL,
    env_json            TEXT         NULL,
    headers_json        TEXT         NULL,
    adapter             VARCHAR(32)  NOT NULL DEFAULT 'paper_search',
    allowed_tools_json  TEXT         NULL,
    disabled_tools_json TEXT         NULL,
    enabled             TINYINT      NOT NULL DEFAULT 1,
    connect_timeout_ms  INT          NOT NULL DEFAULT 30000,
    call_timeout_ms     INT          NOT NULL DEFAULT 60000,
    created_at          VARCHAR(40)  NOT NULL,
    updated_at          VARCHAR(40)  NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_literature_mcp_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文献检索 MCP server 配置';
