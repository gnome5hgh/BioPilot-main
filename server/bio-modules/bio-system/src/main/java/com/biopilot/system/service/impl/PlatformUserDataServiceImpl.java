package com.biopilot.system.service.impl;

import com.biopilot.system.service.PlatformUserDataService;

import com.biopilot.common.oss.core.MinioTemplate;
import java.util.ArrayList;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

/**
 * 平台用户数据清理：删户时清平台表行与对应 OSS 对象。
 *
 * <p>引擎数据（消息/记忆/索引状态/审计）由 Python 清理，平台数据（论文/文件/文档/
 * 引用/项目/定时任务）归 Java。这里是删户流程的 Java 半边，用显式 user_id 的 SQL，
 * 不走租户插件（删户是管理员动作，没有目标用户登录态）。</p>
 *
 * <p>删除方向：先删行、再删对象；对象删除失败只留孤儿，可由后台对账清扫。</p>
 */
@Service
public class PlatformUserDataServiceImpl implements PlatformUserDataService {

    private static final Logger log = LoggerFactory.getLogger(PlatformUserDataService.class);

    private final JdbcTemplate jdbc;
    private final MinioTemplate minio;

    public PlatformUserDataServiceImpl(JdbcTemplate jdbc, MinioTemplate minio) {
        this.jdbc = jdbc;
        this.minio = minio;
    }

    /**
     * 清理该用户的全部平台数据（幂等）。
     *
     * @param userId 目标用户（sys_user.user_id 的字符串形式）
     */
    public void purge(String userId) {
        List<String> objects = new ArrayList<>();
        objects.addAll(ossKeys("bio_file_upload", "oss_key", userId));
        objects.addAll(ossKeys("bio_paper", "oss_key", userId));
        objects.addAll(ossKeys("bio_document", "oss_key", userId));

        // 先删行：引用库 → 论文/文档/文件 → 项目/定时任务
        for (String table : List.of("bio_citation", "bio_paper", "bio_document",
                "bio_file_upload", "bio_project", "bio_schedule_task")) {
            try {
                jdbc.update("DELETE FROM " + table + " WHERE user_id=?", userId);
            } catch (RuntimeException e) {
                log.warn("删户清理跳过 {}（表不存在或不可达）: {}", table, e.getMessage());
            }
        }

        // 行已删，再删对象；失败只留孤儿
        for (String key : objects) {
            if (key == null || key.isBlank()) {
                continue;
            }
            try {
                minio.removeObject(key);
            } catch (RuntimeException e) {
                log.warn("删户对象清理失败（留孤儿） {}: {}", key, e.getMessage());
            }
        }
    }

    private List<String> ossKeys(String table, String column, String userId) {
        try {
            return jdbc.queryForList(
                    "SELECT " + column + " FROM " + table + " WHERE user_id=?", String.class,
                    userId).stream().filter(k -> k != null && !k.isBlank()).toList();
        } catch (RuntimeException e) {
            log.warn("读取 {} 对象键跳过: {}", table, e.getMessage());
            return List.of();
        }
    }
}
