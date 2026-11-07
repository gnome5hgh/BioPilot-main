-- 平台文件表：统一文件表 / OSS 删除队列 / 旧表（迁移期保留）。
-- 与 server/script/sql/biopilot.sql 保持一致；已存在的旧库用 migrations 补齐。
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

