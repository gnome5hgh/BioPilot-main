-- 引用库迁移：新增 bio_citation 与 bio_paper 的引用关联/书目列。
--
-- 适用对象：已跑过旧版本、bio_paper 已存在的部署。执行前先备份数据库。
-- 幂等：建表用 IF NOT EXISTS；加列/索引/外键前先查 information_schema。
--
-- 用法：
--   mysql -uroot biopilot < server/script/sql/migrations/2026-11-02-citation-library.sql
--
-- 回滚：DROP TABLE bio_citation 前先执行
--   ALTER TABLE bio_paper DROP FOREIGN KEY fk_paper_citation,
--     DROP INDEX uk_paper_citation, DROP COLUMN citation_id,
--     DROP COLUMN authors, DROP COLUMN year, DROP COLUMN journal;

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

DROP PROCEDURE IF EXISTS add_paper_column;
DELIMITER //
CREATE PROCEDURE add_paper_column(IN col VARCHAR(64), IN ddl VARCHAR(255))
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bio_paper'
                      AND COLUMN_NAME = col) THEN
        SET @s = CONCAT('ALTER TABLE bio_paper ADD COLUMN ', ddl);
        PREPARE stmt FROM @s;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END //
DELIMITER ;

CALL add_paper_column('citation_id', 'citation_id VARCHAR(64) NULL');
CALL add_paper_column('authors', "authors VARCHAR(1000) NOT NULL DEFAULT ''");
CALL add_paper_column('year', "year VARCHAR(10) NOT NULL DEFAULT ''");
CALL add_paper_column('journal', "journal VARCHAR(300) NOT NULL DEFAULT ''");
DROP PROCEDURE add_paper_column;

-- 一篇论文最多指向一条引用库行
SET @idx = (SELECT COUNT(*) FROM information_schema.STATISTICS
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bio_paper'
               AND INDEX_NAME = 'uk_paper_citation');
SET @s = IF(@idx = 0,
    'ALTER TABLE bio_paper ADD UNIQUE KEY uk_paper_citation (citation_id)',
    'SELECT 1');
PREPARE stmt FROM @s; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- 引用行删除时自动清空论文的 citation_id
SET @fk = (SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bio_paper'
              AND CONSTRAINT_NAME = 'fk_paper_citation');
SET @s = IF(@fk = 0,
    'ALTER TABLE bio_paper ADD CONSTRAINT fk_paper_citation '
    'FOREIGN KEY (citation_id) REFERENCES bio_citation(id) ON DELETE SET NULL',
    'SELECT 1');
PREPARE stmt FROM @s; EXECUTE stmt; DEALLOCATE PREPARE stmt;
