package com.biopilot.file.service;

/** 论文删除时的扩展点：引用库在删除论文的同一事务里清掉对应的引用行。

    定义在论文域、由引用域实现，避免 `bio-catalog` 反向依赖 `bio-citation`。
*/
public interface PaperDeletionHook {

    /** 论文删除前调用（同一事务）。
     *
     * Args:
     *     userId: 归属用户。
     *     paperId: 被删除的论文 id。
     *     citationId: 该论文关联的引用库行 id；未加入引用库时为空。
     */
    void onPaperDeleted(long userId, String paperId, String citationId);
}
