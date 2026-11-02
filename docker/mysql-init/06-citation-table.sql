-- 引用库表：首次建库时创建。bio_paper 由引擎在首次启动时建表，因此这里
-- 不建外键与 bio_paper 的新列；外键与列由
-- server/script/sql/migrations/2026-11-02-citation-library.sql 在 bio_paper
-- 存在后补齐（幂等）。
CREATE TABLE IF NOT EXISTS bio_citation (
    id VARCHAR(64) NOT NULL,
    user_id VARCHAR(191) NOT NULL,
    cite_key VARCHAR(64) NOT NULL,
    entry_type VARCHAR(32) NOT NULL DEFAULT 'article',
    title VARCHAR(500) NOT NULL,
    authors VARCHAR(1000) NOT NULL DEFAULT '',
    year VARCHAR(10) NOT NULL DEFAULT '',
    journal VARCHAR(300) NOT NULL DEFAULT '',
    volume VARCHAR(40) NULL,
    pages VARCHAR(60) NULL,
    doi VARCHAR(200) NULL,
    fields_json MEDIUMTEXT NULL,
    source VARCHAR(20) NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    seq BIGINT NOT NULL AUTO_INCREMENT,
    PRIMARY KEY (id),
    UNIQUE KEY uk_citation_seq (seq),
    UNIQUE KEY uk_citation_user_key (user_id, cite_key),
    KEY idx_citation_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
