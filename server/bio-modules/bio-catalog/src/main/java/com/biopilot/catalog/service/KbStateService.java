package com.biopilot.catalog.service;

import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 论文知识库索引状态机：`bio_paper` 索引列的唯一写者。
 *
 * <p>引擎（Python）没有浏览器登录态，因此本服务的方法都显式带 `user_id`，不走
 * MyBatis 租户插件；条件更新的 rowcount 就是「这次结果是否真正落盘」的返回值。</p>
 *
 * <p>状态迁移：`not_added/queued → indexing → indexed/failed`。成功与失败都要求
 * 当前仍是 `indexing` 且 `kb_enabled=1`——索引期间被移出的论文，结果自然被拒绝，
 * 由引擎撤回刚建好的向量与镜像。</p>
 */
@Service
public class KbStateService {

    private static final int ERROR_LIMIT = 500;

    private final JdbcTemplate jdbc;
    private final TransactionTemplate transaction;

    public KbStateService(JdbcTemplate jdbc, PlatformTransactionManager transactionManager) {
        this.jdbc = jdbc;
        this.transaction = new TransactionTemplate(transactionManager);
    }

    /**
     * 把派生状态收敛到勾选状态这个唯一真相。
     *
     * @param userId           归属用户。
     * @param requeueIndexing  是否把遗留的 `indexing` 重排为 `queued`。只有持索引锁的
     *                         调用方才能置 true——无锁时另一个进程可能正在索引。
     * @return {@code {reset, queued, requeued}} 三条更新各自影响的行数。
     */
    public Map<String, Object> normalize(String userId, boolean requeueIndexing) {
        return transaction.execute(status -> {
            int reset = jdbc.update(
                    "UPDATE bio_paper SET indexed=0, index_status='not_added',"
                            + " index_error=NULL, indexed_at=NULL, chunk_count=0"
                            + " WHERE user_id=? AND kb_enabled=0"
                            + " AND (indexed<>0 OR index_status<>'not_added' OR chunk_count<>0"
                            + " OR index_error IS NOT NULL OR indexed_at IS NOT NULL)",
                    userId);
            int queued = jdbc.update(
                    "UPDATE bio_paper SET index_status='queued', index_error=NULL"
                            + " WHERE user_id=? AND kb_enabled=1 AND index_status='not_added'",
                    userId);
            int requeued = requeueIndexing ? jdbc.update(
                    "UPDATE bio_paper SET index_status='queued', index_error=NULL"
                            + " WHERE user_id=? AND kb_enabled=1 AND index_status='indexing'",
                    userId) : 0;
            Map<String, Object> out = new LinkedHashMap<>();
            out.put("reset", reset);
            out.put("queued", queued);
            out.put("requeued", requeued);
            return out;
        });
    }

    /**
     * 把该用户所有已加入知识库的论文重排为 `queued`（强制重建）。
     *
     * <p>只会重排 `kb_enabled=1` 的行；已移出的论文不参与。索引列仍由本服务
     * 在后续 `/indexing` 与 `/result` 中更新，调用方只负责触发。</p>
     *
     * @param userId 归属用户。
     * @return 实际重排的行数。
     */
    public int requeueAll(String userId) {
        return jdbc.update(
                "UPDATE bio_paper SET index_status='queued', index_error=NULL"
                        + " WHERE user_id=? AND kb_enabled=1",
                userId);
    }

    /**
     * 把仍在知识库的论文置为「索引中」，返回真正被接受的 id。
     *
     * @param userId   归属用户。
     * @param paperIds 本批待索引论文。
     * @return 被接受（`kb_enabled=1`）的论文 id；其余由调用方跳过。
     */
    public List<String> markIndexing(String userId, List<String> paperIds) {
        List<String> ids = sanitize(paperIds);
        if (ids.isEmpty()) {
            return List.of();
        }
        String in = placeholders(ids.size());
        return transaction.execute(status -> {
            List<Object> args = new ArrayList<>();
            args.add(userId);
            args.addAll(ids);
            List<String> accepted = jdbc.queryForList(
                    "SELECT id FROM bio_paper WHERE user_id=? AND kb_enabled=1"
                            + " AND id IN (" + in + ")",
                    String.class, args.toArray());
            if (!accepted.isEmpty()) {
                String acceptedIn = placeholders(accepted.size());
                List<Object> updateArgs = new ArrayList<>();
                updateArgs.add(userId);
                updateArgs.addAll(accepted);
                jdbc.update("UPDATE bio_paper SET index_status='indexing', index_error=NULL"
                        + " WHERE user_id=? AND kb_enabled=1 AND id IN (" + acceptedIn + ")",
                        updateArgs.toArray());
            }
            return accepted;
        });
    }

    /**
     * 批量写入索引结果，返回每篇是否真正落盘。
     *
     * <p>成功要求 `kb_enabled=1 AND index_status='indexing'`；失败额外要求仍是
     * `indexing`——用户期间重新排队后，旧的失败结果不能把 `queued` 改成 `failed`。</p>
     *
     * @param userId  归属用户。
     * @param results 每项 {@code {paper_id, ok, chunks, error}}。
     * @return {@code paper_id → 是否落盘}；未落盘的由引擎撤回向量与镜像。
     */
    public Map<String, Boolean> applyResults(String userId, List<Map<String, Object>> results) {
        Map<String, Boolean> applied = new LinkedHashMap<>();
        if (results == null || results.isEmpty()) {
            return applied;
        }
        String now = OffsetDateTime.now(ZoneOffset.UTC).toString();
        transaction.executeWithoutResult(status -> {
            for (Map<String, Object> item : results) {
                String paperId = stringValue(item.get("paper_id"));
                if (paperId.isEmpty()) {
                    continue;
                }
                boolean ok = Boolean.parseBoolean(stringValue(item.get("ok")));
                int chunks = intValue(item.get("chunks"));
                int rows;
                if (ok) {
                    rows = jdbc.update(
                            "UPDATE bio_paper SET indexed=1, index_status='indexed',"
                                    + " index_error=NULL, indexed_at=?, chunk_count=?"
                                    + " WHERE user_id=? AND id=? AND kb_enabled=1"
                                    + " AND index_status='indexing'",
                            now, Math.max(0, chunks), userId, paperId);
                } else {
                    rows = jdbc.update(
                            "UPDATE bio_paper SET indexed=0, index_status='failed',"
                                    + " index_error=?, chunk_count=0"
                                    + " WHERE user_id=? AND id=? AND kb_enabled=1"
                                    + " AND index_status='indexing'",
                            truncate(stringValue(item.get("error")), ERROR_LIMIT),
                            userId, paperId);
                }
                applied.put(paperId, rows > 0);
            }
        });
        return applied;
    }

    private static List<String> sanitize(List<String> ids) {
        if (ids == null) {
            return List.of();
        }
        List<String> out = new ArrayList<>();
        for (String id : ids) {
            if (id != null && !id.isBlank()) {
                out.add(id);
            }
        }
        return out;
    }

    private static String placeholders(int count) {
        return String.join(",", Collections.nCopies(count, "?"));
    }

    private static String stringValue(Object value) {
        return value == null ? "" : String.valueOf(value).trim();
    }

    private static int intValue(Object value) {
        try {
            return Integer.parseInt(stringValue(value));
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    private static String truncate(String value, int limit) {
        if (value.length() <= limit) {
            return value;
        }
        return value.substring(0, limit);
    }
}
