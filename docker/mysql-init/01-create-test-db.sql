CREATE DATABASE IF NOT EXISTS biopilot_test;
-- 测试库也需要 sys_* 表：Java 测试（AuthFlowTest）连 biopilot_test 并 TRUNCATE
USE biopilot_test;
CREATE TABLE IF NOT EXISTS sys_user (
    user_id     BIGINT       NOT NULL AUTO_INCREMENT COMMENT '用户ID（全局隔离键）',
    user_name   VARCHAR(64)  NOT NULL                COMMENT '登录用户名',
    password    VARCHAR(100) NOT NULL                COMMENT 'BCrypt 摘要',
    nick_name   VARCHAR(64)  NULL                    COMMENT '显示名',
    role        VARCHAR(20)  NOT NULL DEFAULT 'USER' COMMENT '角色键（ADMIN/USER 两档）',
    status      CHAR(1)      NOT NULL DEFAULT '0'    COMMENT '状态（0正常 1停用）',
    create_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id),
    UNIQUE KEY uk_sys_user_name (user_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户信息表';
CREATE TABLE IF NOT EXISTS sys_login_log (
    id          BIGINT      NOT NULL AUTO_INCREMENT COMMENT '日志ID',
    user_name   VARCHAR(64) NULL COMMENT '尝试登录的用户名',
    user_id     BIGINT      NULL COMMENT '关联用户（未知为 NULL）',
    outcome     VARCHAR(10) NOT NULL COMMENT 'success/failed',
    ip          VARCHAR(64) NULL COMMENT '来源 IP',
    create_time DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_login_log_user (user_id, create_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='登录日志表';
-- 项目表：与 server/script/sql/biopilot.sql 等价；测试库也建一份，避免项目域用例缺表
CREATE TABLE IF NOT EXISTS bio_project (
    project_id    VARCHAR(64)  NOT NULL COMMENT '项目ID',
    user_id       VARCHAR(191) NOT NULL COMMENT '归属用户（租户列）',
    name          VARCHAR(50)  NOT NULL COMMENT '项目名称',
    billing_group VARCHAR(64)  NULL COMMENT '计费组（原型字段，保留无逻辑）',
    description   VARCHAR(100) NULL COMMENT '简介',
    create_time   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id),
    KEY idx_project_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目表';
-- 定时任务表：与 server/script/sql/biopilot.sql 等价；测试库也建一份，避免调度用例缺表
CREATE TABLE IF NOT EXISTS bio_schedule_task (
    id               VARCHAR(64)  NOT NULL COMMENT '任务ID',
    user_id          VARCHAR(191) NOT NULL COMMENT '归属用户（租户列）',
    conversation_id  VARCHAR(64)  NOT NULL COMMENT '归属会话',
    name             VARCHAR(200) NOT NULL COMMENT '任务名',
    task             TEXT         NOT NULL COMMENT '到点执行的任务文本',
    interval_minutes INTEGER      NOT NULL COMMENT '执行周期（分钟）',
    paused           INTEGER      NOT NULL DEFAULT 0 COMMENT '1=暂停',
    last_run_at      VARCHAR(40)  NULL COMMENT '上次执行时间（引擎回写）',
    next_run_at      VARCHAR(40)  NOT NULL COMMENT '下次执行时间（引擎回写）',
    created_at       VARCHAR(40)  NOT NULL COMMENT '创建时间',
    PRIMARY KEY (id),
    KEY idx_sched_user (user_id),
    KEY idx_sched_next (next_run_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='定时任务表';
