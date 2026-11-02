package com.biopilot.kb.service;

import java.util.Map;

/** 知识库概览：平台侧统计 + 引擎运行时信息（引擎不可达时降级）。 */
public interface KbOverviewService {

    /**
     * 组装知识库概览。
     *
     * Args:
     *     userId: 归属用户。
     *
     * Returns:
     *     与前端契约一致的状态字典（统计 + 运行时信息）。
     */
    Map<String, Object> snapshot(long userId);
}
