package com.biopilot.file.service;

import com.biopilot.common.oss.core.MinioTemplate;
import com.biopilot.file.domain.FileNames;
import com.biopilot.file.domain.FileObjectKeys;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/**
 * 一次性迁移：把旧 {@code bio_document.content} 回填到 OSS，并写入 {@code bio_file} 的文档行。
 *
 * <p>只在显式打开 {@code biopilot.migration.document-content-to-oss=true} 时运行。
 * 可在迁移 SQL 之前或之后运行：行不存在就补插，行存在但 oss_key 为空就回填；
 * 空正文也写一个空对象，避免迁移后文档永久读不到。完成后顺便把所有
 * {@code bio_file.name_key} 按 Java 的 NFC+trim+lower 口径归一化一次。</p>
 */
@Component
@ConditionalOnProperty(name = "biopilot.migration.document-content-to-oss",
        havingValue = "true")
public class DocumentContentBackfillRunner implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(DocumentContentBackfillRunner.class);

    private final JdbcTemplate jdbc;
    private final MinioTemplate minio;

    public DocumentContentBackfillRunner(JdbcTemplate jdbc, MinioTemplate minio) {
        this.jdbc = jdbc;
        this.minio = minio;
    }

    @Override
    public void run(ApplicationArguments args) {
        backfillDocuments();
        normalizeNameKeys();
    }

    private void backfillDocuments() {
        List<Map<String, Object>> rows;
        try {
            rows = jdbc.queryForList(
                    "SELECT id, user_id, name, content, updated_at FROM bio_document");
        } catch (RuntimeException e) {
            log.info("旧 bio_document 表不存在，跳过文档正文回填");
            return;
        }
        int written = 0;
        int skipped = 0;
        for (Map<String, Object> row : rows) {
            String id = String.valueOf(row.get("id"));
            String userId = String.valueOf(row.get("user_id"));
            String name = FileNames.displayName(
                    row.get("name") == null ? "" : String.valueOf(row.get("name")),
                    200, "未命名.md");
            String content = row.get("content") == null ? "" : String.valueOf(row.get("content"));
            String updatedAt = row.get("updated_at") == null
                    ? FileNames.now() : String.valueOf(row.get("updated_at"));

            String current = jdbc.query(
                    "SELECT oss_key FROM bio_file WHERE kind='document' AND id=? LIMIT 1",
                    rs -> rs.next() ? rs.getString(1) : null, id);
            if (current != null && !current.isBlank()) {
                skipped++;
                continue;
            }
            byte[] data = content.getBytes(StandardCharsets.UTF_8);
            String sha = FileNames.sha256(data);
            String key = FileObjectKeys.document(userId, id, 1, sha, "backfill");
            try {
                minio.putObject(key, data, "text/markdown");
                if (current == null) {
                    jdbc.update("INSERT INTO bio_file (id, user_id, kind, name, name_key,"
                                    + " oss_key, size_bytes, content_type, sha256, version,"
                                    + " source, created_at, updated_at)"
                                    + " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            id, userId, "document", name, FileNames.nameKey(name),
                            key, data.length, "text/markdown", sha, 1, "document",
                            updatedAt, updatedAt);
                } else {
                    jdbc.update("UPDATE bio_file SET oss_key=?, sha256=?, size_bytes=?,"
                                    + " content_type='text/markdown', version=1, updated_at=?"
                                    + " WHERE kind='document' AND id=?",
                            key, sha, data.length, updatedAt, id);
                }
                written++;
            } catch (DuplicateKeyException e) {
                log.error("文档回填遇到同名冲突，已跳过 id={} name={}: {}",
                        id, name, e.getMessage());
            } catch (RuntimeException e) {
                log.warn("文档正文回填失败 id={}: {}", id, e.getMessage());
            }
        }
        log.info("文档正文回填完成：写入 {} 篇，已就绪跳过 {} 篇", written, skipped);
    }

    /** 把所有行的 name_key 收敛到 Java 口径（NFC+trim+lower）；只改不一致的行。 */
    private void normalizeNameKeys() {
        List<Map<String, Object>> rows = jdbc.queryForList(
                "SELECT id, name FROM bio_file");
        int changed = 0;
        for (Map<String, Object> row : rows) {
            String id = String.valueOf(row.get("id"));
            String name = row.get("name") == null ? "" : String.valueOf(row.get("name"));
            try {
                String key = FileNames.nameKey(name);
                int updated = jdbc.update(
                        "UPDATE bio_file SET name_key=? WHERE id=?"
                                + " AND (name_key IS NULL OR name_key<>?)",
                        key, id, key);
                changed += updated;
            } catch (RuntimeException e) {
                log.warn("name_key 归一化跳过 id={} name={}: {}", id, name, e.getMessage());
            }
        }
        log.info("name_key 归一化完成：更新 {} 行", changed);
    }
}
