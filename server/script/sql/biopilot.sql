-- BioPilot 服务端系统表（sys_* 前缀，照搬 cde-standard 规范：幂等建表、只增不改）
-- 库：biopilot（与 Python 侧记忆/会话表同实例）

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

CREATE TABLE IF NOT EXISTS sys_role (
    role_id   BIGINT      NOT NULL AUTO_INCREMENT COMMENT '角色ID',
    role_key  VARCHAR(20) NOT NULL                COMMENT '角色键（ADMIN/USER）',
    role_name VARCHAR(40) NOT NULL                COMMENT '角色名',
    remark    VARCHAR(200) NULL                   COMMENT '备注',
    PRIMARY KEY (role_id),
    UNIQUE KEY uk_sys_role_key (role_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='角色信息表';

CREATE TABLE IF NOT EXISTS sys_user_role (
    user_id BIGINT NOT NULL COMMENT '用户ID',
    role_id BIGINT NOT NULL COMMENT '角色ID',
    PRIMARY KEY (user_id, role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户-角色关联表';

-- 内置两档角色（幂等）
INSERT INTO sys_role (role_key, role_name, remark)
SELECT 'ADMIN', '管理员', '实验室管理员（老师）'
WHERE NOT EXISTS (SELECT 1 FROM sys_role WHERE role_key = 'ADMIN');

INSERT INTO sys_role (role_key, role_name, remark)
SELECT 'USER', '普通用户', '学生' FROM DUAL
WHERE NOT EXISTS (SELECT 1 FROM sys_role WHERE role_key = 'USER');

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

-- 定时任务定义（任务定义列归 Java；执行进度列 last_run_at / next_run_at 由引擎回写）
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
