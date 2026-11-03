package com.biopilot.file.service;

/** 论文标题变化后触发索引重排的跨模块钩子（由 bio-kb 实现，bio-file 只发通知）。 */
public interface PaperRequeueHook {

    /**
     * 标题变化且论文在知识库时调用。
     *
     * @param userId  归属用户
     * @param paperId 论文 id
     */
    void onPaperTitleChanged(long userId, String paperId);
}
