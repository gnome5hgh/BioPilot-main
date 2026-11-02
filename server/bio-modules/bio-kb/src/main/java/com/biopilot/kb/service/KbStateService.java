package com.biopilot.kb.service;

import java.util.List;
import java.util.Map;

/** 论文知识库索引状态机：`bio_paper` 索引列的写者。 */
public interface KbStateService {

    /**
     * 把派生状态收敛到勾选状态这个唯一真相。
     *
     * Args:
     *     userId: 归属用户。
     *     requeueIndexing: 是否把遗留的 `indexing` 重排为 `queued`（只有持索引锁时置 true）。
     *
     * Returns:
     *     {@code {reset, queued, requeued}} 三条更新各自影响的行数。
     */
    Map<String, Object> normalize(String userId, boolean requeueIndexing);

    /** 把该用户所有已加入知识库的论文重排为 `queued`（强制重建）。 */
    int requeueAll(String userId);

    /** 把仍在知识库的论文置为「索引中」，返回真正被接受的 id。 */
    List<String> markIndexing(String userId, List<String> paperIds);

    /** 批量写入索引结果，返回每篇是否真正落盘。 */
    Map<String, Boolean> applyResults(String userId, List<Map<String, Object>> results);
}
