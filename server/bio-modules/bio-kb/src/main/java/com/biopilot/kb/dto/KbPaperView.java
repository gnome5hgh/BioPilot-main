package com.biopilot.kb.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/** 知识库清单里的论文视图：字段与文件管理页的 {@code PaperView} 保持一致。

    两个模块共用同一张 {@code bio_paper}，但读出来的列不同：本视图只覆盖
    知识库关心的身份列与索引状态列，避免 bio-kb 反向依赖 bio-file 的 DTO。
*/
public record KbPaperView(
        String id,
        String title,
        @JsonProperty("file_name") String fileName,
        @JsonProperty("oss_key") String ossKey,
        @JsonProperty("size_bytes") long sizeBytes,
        int indexed,
        @JsonProperty("kb_enabled") int kbEnabled,
        @JsonProperty("citation_id") String citationId,
        String authors,
        String year,
        String journal,
        @JsonProperty("index_status") String indexStatus,
        @JsonProperty("index_error") String indexError,
        @JsonProperty("indexed_at") String indexedAt,
        @JsonProperty("chunk_count") int chunkCount,
        @JsonProperty("created_at") String createdAt) {
}
