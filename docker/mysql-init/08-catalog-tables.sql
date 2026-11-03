-- 平台文件表：数据文件 / 论文目录 / 文档编辑器（容器首启建库）。
-- 与 server/script/sql/biopilot.sql 保持一致；已存在的旧库用 migrations 补齐。
CREATE TABLE IF NOT EXISTS bio_file_upload (
    id           VARCHAR(64)  NOT NULL COMMENT '文件ID',
    user_id      VARCHAR(191) NOT NULL COMMENT '归属用户（租户列）',
    name         VARCHAR(255) NOT NULL COMMENT '原始文件名',
    oss_key      VARCHAR(500) NOT NULL COMMENT 'OSS 对象键',
    size_bytes   BIGINT       NOT NULL DEFAULT 0 COMMENT '字节数',
    content_type VARCHAR(120) NULL COMMENT 'MIME',
    source       VARCHAR(16)  NOT NULL DEFAULT 'upload' COMMENT '来源（upload=用户上传 / artifact=分析产物）',
    created_at   VARCHAR(40)  NOT NULL COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_upload_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='数据文件表';

-- 用户文件同名登记：论文/数据文件/文档共用一个名字空间。
-- 唯一键是权威约束（先占名再写业务行），分析产物不登记（可跨 run 重名）。
CREATE TABLE IF NOT EXISTS bio_user_file (
    id         BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    user_id    VARCHAR(191) NOT NULL COMMENT '归属用户（租户列）',
    kind       VARCHAR(16)  NOT NULL COMMENT '类型（paper/file/document）',
    name_key   VARCHAR(255) NOT NULL COMMENT '归一化名（NFC+trim+lower，唯一键依据）',
    name       VARCHAR(255) NOT NULL COMMENT '展示用原始名',
    ref_id     VARCHAR(64)  NOT NULL COMMENT '业务表主键',
    created_at VARCHAR(40)  NOT NULL COMMENT '占名时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_user_file_name (user_id, name_key),
    UNIQUE KEY uk_user_file_ref (kind, ref_id),
    KEY idx_user_file_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户文件同名登记表';

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
