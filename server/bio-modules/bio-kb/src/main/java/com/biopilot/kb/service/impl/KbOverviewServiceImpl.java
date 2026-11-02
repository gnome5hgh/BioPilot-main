package com.biopilot.kb.service.impl;

import com.biopilot.kb.service.KbOverviewService;

import com.biopilot.common.web.http.AgentInternalClient;
import com.biopilot.kb.dto.KbPaperView;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import com.biopilot.kb.service.KbPaperService;

/**
 * 知识库概览：平台侧统计只读 `bio_paper`，RAG 运行时信息向引擎内部端点取。
 *
 * <p>`bio_paper` 是知识库成员与索引状态的唯一真相：勾选/移出、索引结果都由 Java
 * 落库，因此概览不需要（也不应该）去查 Milvus。统计口径复用
 * {@link KbPaperService#list} 的归一化结果，页面上的统计与「已加入」清单不会互相矛盾。</p>
 *
 * <p>`collection` / `embedding_model` / `running` / `last_run` 属于引擎运行时与
 * RAG 配置，Java 不复制这些规则；引擎不可达时回落空值，统计照常返回。</p>
 */
@Service
public class KbOverviewServiceImpl implements KbOverviewService {

    private final KbPaperService papers;
    private final AgentInternalClient internal;

    public KbOverviewServiceImpl(KbPaperService papers, AgentInternalClient internal) {
        this.papers = papers;
        this.internal = internal;
    }

    /**
     * 组装知识库概览。
     *
     * Args:
     *     userId: 归属用户（由登录态取得）。
     *
     * Returns:
     *     Map: 与前端契约一致的状态字典（统计 + 运行时信息）。
     */
    public Map<String, Object> snapshot(long userId) {
        List<KbPaperView> all = papers.list(userId, "all");
        int kbEnabled = 0;
        int indexed = 0;
        int queued = 0;
        int indexing = 0;
        int failed = 0;
        int chunks = 0;
        String lastIndexedAt = null;
        for (KbPaperView paper : all) {
            if (paper.kbEnabled() != 1) {
                continue;
            }
            kbEnabled++;
            chunks += Math.max(0, paper.chunkCount());
            String status = paper.indexStatus() == null ? "queued" : paper.indexStatus();
            switch (status) {
                case "indexed" -> {
                    indexed++;
                    if (paper.indexedAt() != null
                            && (lastIndexedAt == null
                            || paper.indexedAt().compareTo(lastIndexedAt) > 0)) {
                        lastIndexedAt = paper.indexedAt();
                    }
                }
                case "queued" -> queued++;
                case "indexing" -> indexing++;
                case "failed" -> failed++;
                default -> { }
            }
        }

        Map<String, Object> runtime = internal.kbRuntime(userId);
        if (runtime == null) {
            runtime = Map.of();
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("total_papers", all.size());
        out.put("kb_enabled", kbEnabled);
        out.put("indexed", indexed);
        out.put("queued", queued);
        out.put("indexing", indexing);
        out.put("failed", failed);
        out.put("not_added", all.size() - kbEnabled);
        out.put("chunks", chunks);
        out.put("collection", runtime.getOrDefault("collection", ""));
        out.put("embedding_model", runtime.getOrDefault("embedding_model", ""));
        out.put("last_indexed_at", lastIndexedAt);
        out.put("running", Boolean.TRUE.equals(runtime.get("running")));
        out.put("last_run", runtime.get("last_run"));
        return out;
    }
}
