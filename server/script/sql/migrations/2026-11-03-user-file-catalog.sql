-- 用户文件同名登记表（跨论文/数据文件/文档的唯一名字空间）。
--
-- 部署顺序：先在目标库执行本脚本，再发布服务端代码；服务启动时的
-- UserFileCatalogBackfillRunner 会把存量业务行回填进登记表，并为并发期
-- 产生的同名重复行生成 "原名 (2).ext" 这类新名字（日志会逐条列出）。
--
-- 本脚本可重复执行：建表 IF NOT EXISTS；加列前查 information_schema。

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

-- bio_file_upload 增加来源列：分析产物不参与同名约束（跨 run 重名是正常现象）。
SET @col_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'bio_file_upload'
      AND COLUMN_NAME = 'source'
);
SET @ddl := IF(
    @col_exists = 0,
    'ALTER TABLE bio_file_upload ADD COLUMN source VARCHAR(16) NOT NULL DEFAULT ''upload'' COMMENT ''来源（upload=用户上传 / artifact=分析产物）'' AFTER content_type',
    'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 存量分析产物按 OSS 键前缀回填来源（只此一次；新代码写入时显式赋值）。
UPDATE bio_file_upload
SET source = 'artifact'
WHERE source = 'upload'
  AND oss_key LIKE 'users/%/files/analysis/%';
