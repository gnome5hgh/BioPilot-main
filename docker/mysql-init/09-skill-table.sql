-- 用户技能表：每个用户安装的 agentskills.io 标准形态包。
-- 内容本体存 OSS（users/<uid>/skills/<name>/<content_sha>.zip），本表只存元数据；
-- 一致性方向：对象先落、行后写；卸载先删行、再删对象（孤儿对象可后台清扫）。
-- 内置技能随仓库分发，不入本表、不在页面展示。
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
