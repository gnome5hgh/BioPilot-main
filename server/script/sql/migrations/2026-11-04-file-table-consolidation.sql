-- 文件表合并迁移：bio_paper / bio_file_upload / bio_document / bio_user_file -> bio_file。
--
-- 执行前提：
--   1. 已备份 MySQL 与 MinIO 数据卷；
--   2. 已用新代码启动过一次带 biopilot.migration.document-content-to-oss=true 的实例，
--      把 bio_document.content 回填到 OSS 并写回 oss_key；
--   3. 旧表暂时保留，浏览器 E2E 通过后再执行文件末尾的 DROP。
--
-- name_key 的最终口径是 NFC + trim + lower。SQL 只能做 trim + lower；
-- DocumentContentBackfillRunner 会逐行按 Java 口径归一化一次。
-- 下面用 INSERT（不是 INSERT IGNORE）：跨 kind 同名会直接让迁移失败并暴露冲突，
-- 不允许静默丢行；每段都带 WHERE NOT EXISTS，重复执行不会重复插入。

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

-- 论文：保留 id / oss_key，file_name 映射为 name。
INSERT INTO bio_file
    (id, user_id, kind, name, name_key, oss_key, size_bytes, content_type,
     sha256, version, source, title, authors, year, journal,
     kb_enabled, indexed, index_status, index_error, indexed_at,
     chunk_count, citation_id, created_at, updated_at)
SELECT p.id, p.user_id, 'paper',
       COALESCE(NULLIF(p.file_name, ''), SUBSTRING_INDEX(p.oss_key, '/', -1)),
       LOWER(TRIM(COALESCE(NULLIF(p.file_name, ''), SUBSTRING_INDEX(p.oss_key, '/', -1)))),
       p.oss_key, p.size_bytes, 'application/pdf', NULL, 1, 'paper',
       p.title, p.authors, p.year, p.journal,
       p.kb_enabled, p.indexed, p.index_status, p.index_error, p.indexed_at,
       p.chunk_count, p.citation_id, p.created_at, p.created_at
FROM bio_paper p
WHERE NOT EXISTS (SELECT 1 FROM bio_file f WHERE f.id = p.id);

-- 数据文件：source=upload 归 data（占名），source=artifact 归 artifact（不占名）。
INSERT INTO bio_file
    (id, user_id, kind, name, name_key, oss_key, size_bytes, content_type,
     sha256, version, source, created_at, updated_at)
SELECT u.id, u.user_id,
       CASE WHEN u.source = 'artifact' THEN 'artifact' ELSE 'data' END,
       u.name,
       CASE WHEN u.source = 'artifact' THEN NULL ELSE LOWER(TRIM(u.name)) END,
       u.oss_key, u.size_bytes, u.content_type, NULL, 1,
       CASE WHEN u.source = 'artifact' THEN 'artifact' ELSE 'upload' END,
       u.created_at, u.created_at
FROM bio_file_upload u
WHERE NOT EXISTS (SELECT 1 FROM bio_file f WHERE f.id = u.id);

-- 文档：正文已在第 2 步回填 OSS；这里只迁移元数据。
INSERT INTO bio_file
    (id, user_id, kind, name, name_key, oss_key, size_bytes, content_type,
     sha256, version, source, created_at, updated_at)
SELECT d.id, d.user_id, 'document', d.name, LOWER(TRIM(d.name)),
       COALESCE(d.oss_key, ''), 0, 'text/markdown', NULL, 1, 'document',
       d.updated_at, d.updated_at
FROM bio_document d
WHERE NOT EXISTS (SELECT 1 FROM bio_file f WHERE f.id = d.id);

-- 迁移后核对：三类行数应与旧表一致；name_key 冲突会体现在下面的查询里。
-- SELECT kind, COUNT(*) FROM bio_file GROUP BY kind;
-- SELECT id, user_id, kind, name, name_key FROM bio_file
--  WHERE name_key IS NOT NULL GROUP BY user_id, name_key HAVING COUNT(*) > 1;

-- 浏览器 E2E 通过后再执行（保留旧表用于回滚）：
-- DROP TABLE bio_user_file;
-- DROP TABLE bio_document;
-- DROP TABLE bio_file_upload;
-- DROP TABLE bio_paper;
