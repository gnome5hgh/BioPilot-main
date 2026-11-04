-- BioPilot 服务端系统表（sys_* 前缀，照搬 cde-standard 规范：幂等建表、只增不改）
-- 库：biopilot（与 Python 侧记忆/会话表同实例）

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

CREATE TABLE IF NOT EXISTS sys_role (
    role_id   BIGINT      NOT NULL AUTO_INCREMENT COMMENT '角色ID',
    role_key  VARCHAR(20) NOT NULL                COMMENT '角色键（ADMIN/USER）',
    role_name VARCHAR(40) NOT NULL                COMMENT '角色名',
    remark    VARCHAR(200) NULL                   COMMENT '备注',
    PRIMARY KEY (role_id),
    UNIQUE KEY uk_sys_role_key (role_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='角色信息表';

CREATE TABLE IF NOT EXISTS sys_user_role (
    user_id BIGINT NOT NULL COMMENT '用户ID',
    role_id BIGINT NOT NULL COMMENT '角色ID',
    PRIMARY KEY (user_id, role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户-角色关联表';

-- 内置两档角色（幂等）
INSERT INTO sys_role (role_key, role_name, remark)
SELECT 'ADMIN', '管理员', '实验室管理员（老师）'
WHERE NOT EXISTS (SELECT 1 FROM sys_role WHERE role_key = 'ADMIN');

INSERT INTO sys_role (role_key, role_name, remark)
SELECT 'USER', '普通用户', '学生' FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM sys_role WHERE role_key = 'USER');

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

-- 定时任务定义（任务定义列归 Java；执行进度列 last_run_at / next_run_at 由引擎回写）
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

-- 统一文件表：论文/数据文件/文档/分析产物共用一行，kind 区分类型。
-- 文件正文只存 OSS，本表只存对象键与业务元数据；文档正文不再入库。
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
    kb_enabled      TINYINT      NULL COMMENT '是否加入知识库（仅 paper）',
    indexed         INTEGER      NULL COMMENT '兼容字段：1=已进知识库且索引成功',
    index_status    VARCHAR(20)  NULL COMMENT '索引状态（仅 paper）',
    index_error     VARCHAR(500) NULL COMMENT '最近一次索引失败原因',
    indexed_at      VARCHAR(40)  NULL COMMENT '最近一次索引成功时间',
    chunk_count     INT          NULL COMMENT '分块数',
    citation_id     VARCHAR(64)  NULL COMMENT '引用库行 id（仅 paper）',
    created_at      VARCHAR(40)  NOT NULL COMMENT '创建时间',
    updated_at      VARCHAR(40)  NULL COMMENT '更新时间',
    seq             BIGINT       NOT NULL AUTO_INCREMENT,
    PRIMARY KEY (id),
    UNIQUE KEY uk_file_seq (seq),
    UNIQUE KEY uk_file_name (user_id, name_key),
    KEY idx_file_user_kind (user_id, kind, seq),
    KEY idx_file_run (user_id, run_id),
    KEY idx_file_kb (user_id, kind, kb_enabled, index_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='统一文件表';

-- OSS 删除 outbox：数据库提交后删除对象；失败由定时任务重试。
CREATE TABLE IF NOT EXISTS bio_oss_gc (
    id         BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    oss_key    VARCHAR(500) NOT NULL COMMENT '待删除对象键',
    reason     VARCHAR(32)  NOT NULL COMMENT '删除原因（update/delete/purge）',
    attempts   INT          NOT NULL DEFAULT 0 COMMENT '已尝试次数',
    next_at    VARCHAR(40)  NULL COMMENT '下次尝试时间（ISO）',
    created_at VARCHAR(40)  NOT NULL COMMENT '入队时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_oss_gc_key (oss_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='OSS 删除队列';

-- 文献检索 MCP server 配置（全局管理员配置，无 user_id；密钥字段存 JSON，接口层脱敏）
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

-- 用户技能表：每个用户安装的 agentskills.io 标准形态包（内容本体在 OSS）
CREATE TABLE IF NOT EXISTS bio_skill (
    id           BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    user_id      VARCHAR(191) NOT NULL COMMENT '归属用户（租户列）',
    name         VARCHAR(64)  NOT NULL COMMENT '技能名（agentskills.io 规范）',
    description  VARCHAR(2000) NOT NULL DEFAULT '' COMMENT '描述（L1 清单消费）',
    version      VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '版本（frontmatter metadata.version）',
    source       VARCHAR(16)  NOT NULL COMMENT '来源类型（git/archive）',
    source_url   VARCHAR(1024) NULL COMMENT 'git 来源地址',
    source_ref   VARCHAR(256) NULL COMMENT 'git 分支/标签',
    source_sha   VARCHAR(64)  NULL COMMENT 'git 提交 sha',
    oss_key      VARCHAR(512) NOT NULL COMMENT '技能包 zip 的 OSS 对象键',
    content_sha  VARCHAR(64)  NOT NULL COMMENT 'zip 内容 sha256（本地缓存键）',
    enabled      TINYINT      NOT NULL DEFAULT 1 COMMENT '是否启用',
    installed_at VARCHAR(40)  NOT NULL COMMENT '安装时间（ISO）',
    PRIMARY KEY (id),
    UNIQUE KEY uk_skill_user_name (user_id, name),
    KEY idx_skill_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户技能表';

-- 引用库表：每个用户一份，代理导出 .bib 与勾选加入。
-- 容器首启由 docker/mysql-init/06-citation-table.sql 建同名表，两份必须保持等价。
CREATE TABLE IF NOT EXISTS bio_citation (
    id           VARCHAR(64)  NOT NULL COMMENT '主键',
    user_id      VARCHAR(191) NOT NULL COMMENT '归属用户（租户列）',
    cite_key     VARCHAR(64)  NOT NULL COMMENT '引用键（用户内唯一）',
    entry_type   VARCHAR(32)  NOT NULL DEFAULT 'article' COMMENT 'BibTeX 条目类型',
    title        VARCHAR(500) NOT NULL COMMENT '标题',
    authors      VARCHAR(1000) NOT NULL DEFAULT '' COMMENT '作者',
    year         VARCHAR(10)  NOT NULL DEFAULT '' COMMENT '年份',
    journal      VARCHAR(300) NOT NULL DEFAULT '' COMMENT '期刊',
    volume       VARCHAR(40)  NULL COMMENT '卷',
    pages        VARCHAR(60)  NULL COMMENT '页码',
    doi          VARCHAR(200) NULL COMMENT 'DOI',
    fields_json  MEDIUMTEXT   NULL COMMENT '其余 BibTeX 字段（JSON）',
    source       VARCHAR(20)  NOT NULL COMMENT '来源（manual/agent）',
    created_at   VARCHAR(40)  NOT NULL COMMENT '创建时间（ISO）',
    seq          BIGINT       NOT NULL AUTO_INCREMENT COMMENT '插入序',
    PRIMARY KEY (id),
    UNIQUE KEY uk_citation_seq (seq),
    UNIQUE KEY uk_citation_user_key (user_id, cite_key),
    KEY idx_citation_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='引用库';
