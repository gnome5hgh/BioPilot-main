-- 知识库索引状态归引擎：bio_file 的索引派生列退役，唯一落点改为引擎的
-- bio_rag_paper_status（引擎独占写，Java 只读展示）。
--
-- 执行前提：先停引擎与 server（迁移期间不应有新的状态写入）。
-- 引擎侧 _SCHEMA 也有同款建表语句（CREATE IF NOT EXISTS），本脚本自带一份
-- 是为了让「搬数据」与「删列」在引擎启动前一次完成。
USE biopilot;

-- 1. 索引状态表：逐篇一行；「未加入知识库」= 无行，行存在即进入过索引流程。
CREATE TABLE IF NOT EXISTS bio_rag_paper_status (
    user_id      VARCHAR(191) NOT NULL COMMENT '归属用户（行级隔离）',
    paper_id     VARCHAR(64)  NOT NULL COMMENT '平台论文 id（bio_file.id）',
    index_status VARCHAR(20)  NOT NULL COMMENT 'queued/indexing/indexed/failed',
    indexed      TINYINT      NOT NULL DEFAULT 0 COMMENT '1=索引成功（与 index_status=indexed 同步维护）',
    index_error  VARCHAR(500) NULL COMMENT '最近一次失败原因（截断存储）',
    indexed_at   VARCHAR(40)  NULL COMMENT '最近一次索引成功时间（ISO 字符串）',
    chunk_count  INT          NOT NULL DEFAULT 0 COMMENT '向量库块数（对账基准）',
    updated_at   VARCHAR(40)  NOT NULL COMMENT '最近写入时间（ISO 字符串）',
    PRIMARY KEY (user_id, paper_id),
    KEY idx_paper_status_state (user_id, index_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='论文索引状态（引擎独占写）';

-- 2. 存量状态搬迁：只搬已勾选且进入过流程的行（queued/indexing/indexed/failed）。
--    not_added 与未勾选的行不搬——它们在新模型里等价于「无行」。
INSERT IGNORE INTO bio_rag_paper_status
    (user_id, paper_id, index_status, indexed, index_error, indexed_at, chunk_count, updated_at)
SELECT user_id, id, index_status,
       COALESCE(indexed, 0), index_error, indexed_at, COALESCE(chunk_count, 0),
       COALESCE(indexed_at, NOW(3))
  FROM bio_file
 WHERE kind='paper' AND kb_enabled=1
   AND index_status IS NOT NULL AND index_status <> 'not_added';

-- 3. bio_file 退役索引派生列；勾选真相 kb_enabled 保留（Java 写）。
ALTER TABLE bio_file
    DROP INDEX idx_file_kb,
    ADD KEY idx_file_kb (user_id, kind, kb_enabled),
    DROP COLUMN indexed,
    DROP COLUMN index_status,
    DROP COLUMN index_error,
    DROP COLUMN indexed_at,
    DROP COLUMN chunk_count;
