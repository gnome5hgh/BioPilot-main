package com.biopilot.kb.service.impl;

import com.biopilot.common.web.http.AgentInternalClient;
import com.biopilot.file.service.PaperRequeueHook;
import com.biopilot.kb.service.KbStateService;
import org.springframework.stereotype.Component;

/** 文件域标题变化 → 知识库域重排该篇并唤醒引擎。 */
@Component
public class KbPaperRequeueHook implements PaperRequeueHook {

    private final KbStateService state;
    private final AgentInternalClient internal;

    public KbPaperRequeueHook(KbStateService state, AgentInternalClient internal) {
        this.state = state;
        this.internal = internal;
    }

    @Override
    public void onPaperTitleChanged(long userId, String paperId) {
        state.requeue(String.valueOf(userId), paperId);
        internal.kbSync(userId);
    }
}
