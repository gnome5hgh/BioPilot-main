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
