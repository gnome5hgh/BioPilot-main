-- 用户技能表（新库由 docker/mysql-init/09-skill-table.sql 与 biopilot.sql 直接建表）。
-- 幂等：存量库升级时执行本文件。
CREATE TABLE IF NOT EXISTS bio_skill (
    id           BIGINT       NOT NULL AUTO_INCREMENT COMMENT '主键',
    user_id      VARCHAR(191) NOT NULL COMMENT '归属用户（租户列）',
    name         VARCHAR(64)  NOT NULL COMMENT '技能名（agentskills.io 规范）',
    description  VARCHAR(2000) NOT NULL DEFAULT '' COMMENT '描述（L1 清单消费）',
    version      VARCHAR(64)  NOT NULL DEFAULT '' COMMENT '版本（frontmatter metadata.version）',
    source       VARCHAR(16)  NOT NULL COMMENT '来源类型（git/archive）',
    source_url   VARCHAR(1024) NULL COMMENT 'git 来源地址',
    source_ref   VARCHAR(256) NULL COMMENT 'git 分支/标签',
    source_sha   VARCHAR(64)  NULL COMMENT 'git 提交 sha',
    oss_key      VARCHAR(512) NOT NULL COMMENT '技能包 zip 的 OSS 对象键',
    content_sha  VARCHAR(64)  NOT NULL COMMENT 'zip 内容 sha256（本地缓存键）',
    enabled      TINYINT      NOT NULL DEFAULT 1 COMMENT '是否启用',
    installed_at VARCHAR(40)  NOT NULL COMMENT '安装时间（ISO）',
    PRIMARY KEY (id),
    UNIQUE KEY uk_skill_user_name (user_id, name),
    KEY idx_skill_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户技能表';
