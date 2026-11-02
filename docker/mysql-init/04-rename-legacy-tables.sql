-- 容器首启时的兼容迁移：把已有数据卷里的旧表名改成规范名。
--
-- 全新库没有任何旧表，本脚本是空操作；已有数据卷升级时由 MySQL 首启流程执行。
-- 逻辑与 server/script/sql/migrations/2026-11-02-rename-tables.sql 等价。

USE biopilot;

DROP PROCEDURE IF EXISTS rename_biopilot_table;
DELIMITER //
CREATE PROCEDURE rename_biopilot_table(IN old_name VARCHAR(64), IN new_name VARCHAR(64))
BEGIN
    DECLARE old_exists INT DEFAULT 0;
    DECLARE new_exists INT DEFAULT 0;

    SELECT COUNT(*) INTO old_exists
      FROM information_schema.TABLES
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = old_name;
    SELECT COUNT(*) INTO new_exists
      FROM information_schema.TABLES
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = new_name;

    IF old_exists = 1 AND new_exists = 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = '旧表与新表同时存在，请先人工合并数据后再执行迁移';
    ELSEIF old_exists = 1 AND new_exists = 0 THEN
        SET @ddl = CONCAT('RENAME TABLE `', old_name, '` TO `', new_name, '`');
        PREPARE stmt FROM @ddl;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END //
DELIMITER ;

CALL rename_biopilot_table('blocks', 'bio_memory_block');
CALL rename_biopilot_table('block_history', 'bio_memory_block_history');
CALL rename_biopilot_table('consolidation_cursor', 'bio_memory_consolidation_cursor');
CALL rename_biopilot_table('audit_event', 'bio_security_audit_event');
CALL rename_biopilot_table('uploaded_file', 'bio_file_upload');
CALL rename_biopilot_table('scheduled_task', 'bio_schedule_task');
CALL rename_biopilot_table('papers', 'bio_paper');
CALL rename_biopilot_table('documents', 'bio_document');
CALL rename_biopilot_table('messages', 'bio_message');
CALL rename_biopilot_table('agent_state', 'bio_agent_state');
CALL rename_biopilot_table('biopilot_project', 'bio_project');

DROP PROCEDURE IF EXISTS rename_biopilot_table;
