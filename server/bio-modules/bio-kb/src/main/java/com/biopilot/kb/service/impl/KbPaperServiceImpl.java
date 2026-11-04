package com.biopilot.kb.service.impl;

import com.biopilot.common.web.http.AgentInternalClient;
import com.biopilot.kb.dto.KbPaperView;
import com.biopilot.kb.service.KbPaperService;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

/**
 * 知识库勾选与清单：直接操作 {@code bio_paper} 的 kb 列。
 *
 * <p>这里用显式 {@code user_id} 的 SQL 而不是 MyBatis 租户插件，与
 * {@code KbStateService} 同一套写法：知识库状态的读写方包括引擎内部调用，
 * 没有浏览器登录态，租户插件不可依赖。</p>
 */
@Service
public class KbPaperServiceImpl implements KbPaperService {

    private static final String SELECT_PAPERS =
            "SELECT id, title, name AS file_name, oss_key, size_bytes, indexed, kb_enabled,"
                    + " citation_id, authors, year, journal, index_status, index_error,"
                    + " indexed_at, chunk_count, created_at"
                    + " FROM bio_file WHERE kind='paper' AND user_id=? ORDER BY seq DESC";

    private final JdbcTemplate jdbc;
    private final AgentInternalClient internal;

    public KbPaperServiceImpl(JdbcTemplate jdbc, AgentInternalClient internal) {
        this.jdbc = jdbc;
        this.internal = internal;
    }

    @Override
    public List<KbPaperView> list(long userId, String filter) {
        List<KbPaperView> rows = jdbc.query(SELECT_PAPERS, this::view, String.valueOf(userId));
        if ("in".equals(filter)) {
            return rows.stream().filter(row -> row.kbEnabled() == 1).toList();
        }
        if ("out".equals(filter)) {
            return rows.stream().filter(row -> row.kbEnabled() == 0).toList();
        }
        return rows;
    }

    @Override
    public int add(long userId, List<String> paperIds) {
        List<String> ids = clean(paperIds);
        if (ids.isEmpty()) {
            return 0;
        }
        int count = updateKb(userId, ids, true);
        internal.kbSync(userId);
        return count;
    }

    @Override
    public int remove(long userId, List<String> paperIds) {
        List<String> ids = clean(paperIds);
        if (ids.isEmpty()) {
            return 0;
        }
        int count = updateKb(userId, ids, false);
        internal.kbSync(userId);
        return count;
    }

    @Override
    public int retry(long userId, List<String> paperIds) {
        List<String> ids = clean(paperIds);
        if (ids.isEmpty()) {
            return 0;
        }
        List<Object> args = new ArrayList<>();
        args.add(String.valueOf(userId));
        args.addAll(ids);
        int count = jdbc.update(
                "UPDATE bio_file SET index_status='queued', index_error=NULL"
                        + " WHERE kind='paper' AND user_id=? AND kb_enabled=1"
                        + " AND id IN (" + placeholders(ids.size()) + ")",
                args.toArray());
        internal.kbSync(userId);
        return count;
    }

    /** 勾选与状态复位同一条 UPDATE：移出时把索引派生列一起清空。 */
    private int updateKb(long userId, List<String> ids, boolean enabled) {
        List<Object> args = new ArrayList<>();
        args.add(String.valueOf(userId));
        args.addAll(ids);
        if (!enabled) {
            return jdbc.update(
                    "UPDATE bio_file SET kb_enabled=0, indexed=0, index_status='not_added',"
                            + " index_error=NULL, indexed_at=NULL, chunk_count=0"
                            + " WHERE kind='paper' AND user_id=? AND id IN ("
                            + placeholders(ids.size()) + ")",
                    args.toArray());
        }
        // 已在库里的论文重复勾选不重置状态：重置会把 ready 打回 queued，
        // 白白触发一次全量重建。失败论文的重试走独立的 retry 端点。
        return jdbc.update(
                "UPDATE bio_file SET kb_enabled=1, indexed=0, index_status='queued',"
                        + " index_error=NULL, indexed_at=NULL, chunk_count=0"
                        + " WHERE kind='paper' AND user_id=? AND kb_enabled=0 AND id IN ("
                        + placeholders(ids.size()) + ")",
                args.toArray());
    }

    private KbPaperView view(ResultSet rs, int rowNum) throws SQLException {
        String ossKey = rs.getString("oss_key");
        String fileName = rs.getString("file_name");
        if (fileName == null || fileName.isBlank()) {
            fileName = ossKey == null ? "" : ossKey.substring(ossKey.lastIndexOf('/') + 1);
        }
        int kbEnabled = rs.getInt("kb_enabled");
        int indexed = rs.getInt("indexed");
        String status;
        int chunks;
        if (kbEnabled != 1) {
            // 勾选是「是否在知识库」的唯一真相：未勾选时索引列一律按未加入展示
            status = "not_added";
            chunks = 0;
        } else {
            status = rs.getString("index_status");
            if (status == null || status.isBlank()) {
                status = indexed == 1 ? "indexed" : "queued";
            }
            chunks = rs.getInt("chunk_count");
        }
        return new KbPaperView(
                rs.getString("id"), rs.getString("title"), fileName, ossKey,
                rs.getLong("size_bytes"), indexed, kbEnabled, rs.getString("citation_id"),
                nullToEmpty(rs.getString("authors")), nullToEmpty(rs.getString("year")),
                nullToEmpty(rs.getString("journal")), status, rs.getString("index_error"),
                rs.getString("indexed_at"), chunks, rs.getString("created_at"));
    }

    private static String nullToEmpty(String value) {
        return value == null ? "" : value;
    }

    private static List<String> clean(List<String> ids) {
        if (ids == null) {
            return List.of();
        }
        return ids.stream()
                .filter(id -> id != null && !id.isBlank())
                .toList();
    }

    private static String placeholders(int count) {
        return String.join(",", Collections.nCopies(count, "?"));
    }
}
