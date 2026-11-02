package com.biopilot.catalog.service;

import com.biopilot.common.oss.core.MinioTemplate;
import com.biopilot.common.pdf.PdfMetadataExtractor;
import com.biopilot.common.web.http.AgentInternalClient;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** 启动时异步补齐历史论文标题（`bio_paper.title=''`）。

    标题提取已归 Java：旧库里的直传论文在本次改造前没有标题，平台需要一次性把它们
    从 OSS 原文补齐，否则检索块没有标题前缀、引用库也无法生成条目。任务在后台线程
    执行，不阻塞启动；只处理空标题行，幂等。补完之后按用户触发一次知识库重索引。

    跨用户扫描走 JdbcTemplate（绕过租户插件）——这是显式的系统级数据修复，不是业务读。
*/
@Component
@ConditionalOnProperty(name = "biopilot.backfill-titles", havingValue = "true",
        matchIfMissing = true)
public class PaperTitleBackfillRunner implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(PaperTitleBackfillRunner.class);

    private final JdbcTemplate jdbc;
    private final MinioTemplate minio;
    private final PdfMetadataExtractor metadata;
    private final AgentInternalClient internal;

    public PaperTitleBackfillRunner(JdbcTemplate jdbc, MinioTemplate minio,
                                    PdfMetadataExtractor metadata,
                                    AgentInternalClient internal) {
        this.jdbc = jdbc;
        this.minio = minio;
        this.metadata = metadata;
        this.internal = internal;
    }

    @Override
    public void run(ApplicationArguments args) {
        Thread.ofVirtual().name("paper-title-backfill").start(this::backfill);
    }

    private void backfill() {
        try {
            List<Map<String, Object>> rows = jdbc.queryForList(
                    "SELECT id, user_id, oss_key FROM bio_paper WHERE title=''");
            if (rows.isEmpty()) {
                return;
            }
            Map<String, List<String>> touched = new HashMap<>();
            int filled = 0;
            for (Map<String, Object> row : rows) {
                String id = String.valueOf(row.get("id"));
                try {
                    byte[] data = minio.getObject(String.valueOf(row.get("oss_key")));
                    String title = metadata.extractTitle(data);
                    if (title.isBlank()) {
                        continue;
                    }
                    jdbc.update("UPDATE bio_paper SET title=? WHERE id=?", title, id);
                    String userId = String.valueOf(row.get("user_id"));
                    touched.computeIfAbsent(userId, key -> new ArrayList<>()).add(id);
                    filled += 1;
                } catch (RuntimeException e) {
                    log.warn("标题回填失败 paper={}: {}", id, e.getMessage());
                }
            }
            // 标题进了检索块前缀：回填成功后必须重建这些篇，先置排队再唤醒索引器
            touched.forEach((userId, ids) -> {
                String in = String.join(",", java.util.Collections.nCopies(ids.size(), "?"));
                Object[] args = new Object[ids.size() + 1];
                args[0] = userId;
                for (int i = 0; i < ids.size(); i++) {
                    args[i + 1] = ids.get(i);
                }
                jdbc.update("UPDATE bio_paper SET index_status='queued', index_error=NULL"
                        + " WHERE user_id=? AND kb_enabled=1 AND id IN (" + in + ")", args);
                try {
                    internal.kbSync(Long.parseLong(userId));
                } catch (NumberFormatException e) {
                    log.warn("标题回填后跳过唤醒：user_id 非数字 {}", userId);
                }
            });
            log.info("标题回填完成：扫描 {} 篇，补齐 {} 篇", rows.size(), filled);
        } catch (RuntimeException e) {
            log.warn("标题回填任务失败", e);
        }
    }
}
