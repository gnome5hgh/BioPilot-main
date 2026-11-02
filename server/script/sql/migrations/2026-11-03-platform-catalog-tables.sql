-- 平台文件表归属 Java：已存在的旧库一次性补齐（幂等）。
-- 执行顺序：先在旧库上跑 2026-11-02-rename-tables.sql（旧表名 → bio_*），再跑本文件。
-- 新建库由 server/script/sql/biopilot.sql 与 docker/mysql-init 直接建表。

CREATE TABLE IF NOT EXISTS bio_file_upload (
    id           VARCHAR(64)  NOT NULL COMMENT '文件ID',
    user_id      VARCHAR(191) NOT NULL COMMENT '归属用户（租户列）',
    name         VARCHAR(255) NOT NULL COMMENT '原始文件名',
    oss_key      VARCHAR(500) NOT NULL COMMENT 'OSS 对象键',
    size_bytes   BIGINT       NOT NULL DEFAULT 0 COMMENT '字节数',
    content_type VARCHAR(120) NULL COMMENT 'MIME',
    created_at   VARCHAR(40)  NOT NULL COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_upload_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据文件表';

CREATE TABLE IF NOT EXISTS bio_paper (
    id             VARCHAR(64)  NOT NULL COMMENT '论文ID',
    user_id        VARCHAR(191) NOT NULL COMMENT '归属用户（租户列）',
    title          VARCHAR(500) NOT NULL COMMENT '标题（Java 提取；宁空勿错）',
    file_name      VARCHAR(255) NULL COMMENT '原始文件名（展示/查重；不参与标题）',
    oss_key        VARCHAR(500) NOT NULL COMMENT 'OSS 对象键',
    size_bytes     BIGINT       NOT NULL DEFAULT 0 COMMENT '字节数',
    indexed        INTEGER      NOT NULL DEFAULT 0 COMMENT '兼容字段：1=已进知识库且索引成功',
    kb_enabled     TINYINT      NOT NULL DEFAULT 0 COMMENT '是否加入知识库',
    citation_id    VARCHAR(64)  NULL COMMENT '引用库行 id',
    authors        VARCHAR(1000) NOT NULL DEFAULT '' COMMENT '作者（Java 写）',
    year           VARCHAR(10)  NOT NULL DEFAULT '' COMMENT '年份（Java 写）',
    journal        VARCHAR(300) NOT NULL DEFAULT '' COMMENT '期刊/会议（Java 写）',
    index_status   VARCHAR(20)  NOT NULL DEFAULT 'not_added' COMMENT '索引状态',
    index_error    VARCHAR(500) NULL COMMENT '最近一次索引失败原因',
    indexed_at     VARCHAR(40)  NULL COMMENT '最近一次索引成功时间',
    chunk_count    INT          NOT NULL DEFAULT 0 COMMENT '分块数',
    created_at     VARCHAR(40)  NOT NULL COMMENT '创建时间',
    seq            BIGINT       NOT NULL AUTO_INCREMENT,
    PRIMARY KEY (id),
    UNIQUE KEY uk_papers_seq (seq),
    KEY idx_papers_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='论文目录表';

CREATE TABLE IF NOT EXISTS bio_document (
    id         VARCHAR(64)  NOT NULL COMMENT '文档ID',
    user_id    VARCHAR(191) NOT NULL COMMENT '归属用户（租户列）',
    name       VARCHAR(200) NOT NULL COMMENT '文档名',
    content    MEDIUMTEXT   NULL COMMENT 'markdown 全文',
    oss_key    VARCHAR(500) NULL COMMENT 'OSS 对象键',
    updated_at VARCHAR(40)  NOT NULL COMMENT '更新时间',
    seq        BIGINT       NOT NULL AUTO_INCREMENT,
    PRIMARY KEY (id),
    UNIQUE KEY uk_documents_seq (seq),
    KEY idx_documents_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档表';

-- 旧版只有 indexed 布尔值：补 file_name 供展示/查重；indexed=1 视为已加入知识库
UPDATE bio_paper SET file_name = SUBSTRING_INDEX(oss_key, '/', -1)
WHERE file_name IS NULL OR file_name = '';

UPDATE bio_paper SET kb_enabled = 1, index_status = 'indexed',
    indexed_at = COALESCE(indexed_at, created_at)
WHERE indexed = 1 AND kb_enabled = 0 AND index_status = 'not_added';
