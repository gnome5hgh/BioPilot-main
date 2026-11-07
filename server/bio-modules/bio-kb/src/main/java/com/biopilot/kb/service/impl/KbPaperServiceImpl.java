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
 * 知识库勾选与清单：Java 只写勾选真相 {@code kb_enabled}，索引状态一律只读。
 *
 * <p>索引状态（排队/索引中/成功/失败、块数）的唯一落点是引擎的
 * {@code bio_rag_paper_status} 表（引擎独占写），本模块清单查询以 LEFT JOIN
 * 带出用于展示；重试与标题变更重建经 {@code /internal/kb/sync} 携带论文 id
 * 通知引擎，由引擎改自己的状态表。这里用显式 {@code user_id} 的 SQL 而不是
 * MyBatis 租户插件，与跨栈只读引擎表的登记约定一致。</p>
 */
@Service
public class KbPaperServiceImpl implements KbPaperService {

    private static final String SELECT_PAPERS =
            "SELECT f.id, f.title, f.name AS file_name, f.oss_key, f.size_bytes,"
                    + " s.indexed, f.kb_enabled, f.citation_id, f.authors, f.year,"
                    + " f.journal, s.index_status, s.index_error, s.indexed_at,"
                    + " s.chunk_count, f.created_at"
                    + " FROM bio_file f LEFT JOIN bio_rag_paper_status s"
                    + " ON s.user_id=f.user_id AND s.paper_id=f.id"
                    + " WHERE f.kind='paper' AND f.user_id=? ORDER BY f.seq DESC";

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
        // 重试 = 通知引擎把状态行重排为 queued（状态唯一落点在引擎表）。
        // 返回值是「确在本人知识库里的论文数」——不存在/未勾选的 id 不冒充成功；
        // 引擎侧是否重排成功由状态表展示，这里只对通知范围负责。
        Integer known = jdbc.queryForObject(
                "SELECT COUNT(*) FROM bio_file WHERE kind='paper' AND user_id=?"
                        + " AND kb_enabled=1 AND id IN (" + placeholders(ids.size()) + ")",
                Integer.class, prepended(String.valueOf(userId), ids).toArray());
        internal.kbSync(userId, ids, List.of());
        return known == null ? 0 : known;
    }

    /** user_id 打头的参数列表（IN 查询的实参顺序：先 user_id 再 ids）。 */
    private static List<Object> prepended(String userId, List<String> ids) {
        List<Object> args = new ArrayList<>();
        args.add(userId);
        args.addAll(ids);
        return args;
    }

    /** 勾选迁移只写 kb_enabled；索引派生状态由引擎在自己的表里收敛。 */
    private int updateKb(long userId, List<String> ids, boolean enabled) {
        List<Object> args = new ArrayList<>();
        args.add(String.valueOf(userId));
        args.addAll(ids);
        if (!enabled) {
            return jdbc.update(
                    "UPDATE bio_file SET kb_enabled=0"
                            + " WHERE kind='paper' AND user_id=? AND id IN ("
                            + placeholders(ids.size()) + ")",
                    args.toArray());
        }
        // 已在库里的论文重复勾选不动：重排会让已就绪论文白白重建一轮；
        // 失败论文的重试走独立的 retry 端点。
        return jdbc.update(
                "UPDATE bio_file SET kb_enabled=1"
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
            // 勾选是「是否在知识库」的唯一真相：未勾选时索引状态一律按未加入展示
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
