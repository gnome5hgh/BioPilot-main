package com.biopilot.kb.service.impl;

import com.biopilot.common.web.http.AgentInternalClient;
import com.biopilot.file.service.PaperRequeueHook;
import java.util.List;
import org.springframework.stereotype.Component;

/** 文件域标题变化 → 通知引擎把该篇重排为 queued 并唤醒索引（状态落点在引擎表）。 */
@Component
public class KbPaperRequeueHook implements PaperRequeueHook {

    private final AgentInternalClient internal;

    public KbPaperRequeueHook(AgentInternalClient internal) {
        this.internal = internal;
    }

    @Override
    public void onPaperTitleChanged(long userId, String paperId) {
        internal.kbSync(userId, List.of(), List.of(paperId));
    }
}
