-- 定时任务表（与 server/script/sql/biopilot.sql 等价条目；容器首启建）
USE biopilot;
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
