-- local 域退役 + bio_rag_index_state 隔离键改名：项目已只服务多用户平台，
-- 引擎不再有无用户的运行形态（单机/评测脚本必须显式传真实 user_id）。
-- 执行前提：先停引擎与 server。local 行是评测/单机时代的索引账本，可丢。
-- 幂等：全部步骤按 information_schema 条件化，可重复执行、中断后可续跑。
-- 说明：本脚本触及引擎表（bio_rag_index_state）的改名类 DDL——这类变更无法
-- 经 _ADDITIVE_COLUMNS 表达，是「引擎表 DDL 落点在 _SCHEMA」约定的一次性例外，
-- 完成后引擎启动即与 _SCHEMA 一致。
USE biopilot;

DROP PROCEDURE IF EXISTS migrate_index_state_user_id;
DELIMITER //
CREATE PROCEDURE migrate_index_state_user_id()
BEGIN
    DECLARE col VARCHAR(64);
    DECLARE tbl INT;

    -- 1. 隔离键改名（仅当旧列名还在；local 行随改名前删除）
    SELECT COUNT(*) INTO tbl FROM information_schema.TABLES
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bio_rag_index_state';
    IF tbl = 1 THEN
        SELECT COUNT(*) INTO col FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bio_rag_index_state'
           AND COLUMN_NAME = 'user_domain';
        IF col = 1 THEN
            DELETE FROM bio_rag_index_state WHERE user_domain = 'local';
            ALTER TABLE bio_rag_index_state RENAME COLUMN user_domain TO user_id;
        END IF;
    END IF;

    -- 2. 引擎四表的 user_id 列默认值移除（新写入必须显式携带归属；历史行不动）
    SET @ddl = (SELECT IF(COUNT(*),
        'ALTER TABLE bio_message ALTER COLUMN user_id DROP DEFAULT', 'SELECT 1')
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bio_message'
          AND COLUMN_NAME = 'user_id' AND COLUMN_DEFAULT IS NOT NULL);
    PREPARE s FROM @ddl; EXECUTE s; DEALLOCATE PREPARE s;

    SET @ddl = (SELECT IF(COUNT(*),
        'ALTER TABLE bio_memory_block ALTER COLUMN user_id DROP DEFAULT', 'SELECT 1')
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bio_memory_block'
          AND COLUMN_NAME = 'user_id' AND COLUMN_DEFAULT IS NOT NULL);
    PREPARE s FROM @ddl; EXECUTE s; DEALLOCATE PREPARE s;

    SET @ddl = (SELECT IF(COUNT(*),
        'ALTER TABLE bio_memory_block_history ALTER COLUMN user_id DROP DEFAULT', 'SELECT 1')
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bio_memory_block_history'
          AND COLUMN_NAME = 'user_id' AND COLUMN_DEFAULT IS NOT NULL);
    PREPARE s FROM @ddl; EXECUTE s; DEALLOCATE PREPARE s;

    SET @ddl = (SELECT IF(COUNT(*),
        'ALTER TABLE bio_agent_state ALTER COLUMN user_id DROP DEFAULT', 'SELECT 1')
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'bio_agent_state'
          AND COLUMN_NAME = 'user_id' AND COLUMN_DEFAULT IS NOT NULL);
    PREPARE s FROM @ddl; EXECUTE s; DEALLOCATE PREPARE s;
END //
DELIMITER ;

CALL migrate_index_state_user_id();
DROP PROCEDURE IF EXISTS migrate_index_state_user_id;

-- 3. 测试库追补（仅本机 biopilot_test：其 bio_message 建表早于多用户改造，
--    增量补列从未落到它。生产库无此需求；新测试库由 _SCHEMA 直建新形态。）
DROP PROCEDURE IF EXISTS migrate_test_db_message_user_id;
DELIMITER //
CREATE PROCEDURE migrate_test_db_message_user_id()
BEGIN
    DECLARE col INT;
    SELECT COUNT(*) INTO col FROM information_schema.COLUMNS
     WHERE TABLE_SCHEMA = 'biopilot_test' AND TABLE_NAME = 'bio_message'
       AND COLUMN_NAME = 'user_id';
    IF col = 0 THEN
        ALTER TABLE biopilot_test.bio_message
            ADD COLUMN user_id VARCHAR(191) NOT NULL AFTER agent_id;
    END IF;
END //
DELIMITER ;

CALL migrate_test_db_message_user_id();
DROP PROCEDURE IF EXISTS migrate_test_db_message_user_id;
