package com.biopilot.catalog.dto;

import com.biopilot.catalog.domain.BioPaper;
import com.fasterxml.jackson.annotation.JsonProperty;

/** 论文列表/详情的对外视图（snake_case 与前端既有契约一致）。 */
public record PaperView(
        String id,
        String title,
        @JsonProperty("file_name") String fileName,
        @JsonProperty("oss_key") String ossKey,
        @JsonProperty("size_bytes") long sizeBytes,
        int indexed,
        @JsonProperty("kb_enabled") int kbEnabled,
        @JsonProperty("index_status") String indexStatus,
        @JsonProperty("index_error") String indexError,
        @JsonProperty("indexed_at") String indexedAt,
        @JsonProperty("chunk_count") int chunkCount,
        @JsonProperty("created_at") String createdAt) {

    public static PaperView from(BioPaper p) {
        String fileName = p.getFileName();
        if (fileName == null || fileName.isBlank()) {
            fileName = p.getOssKey() == null ? "" : p.getOssKey().substring(p.getOssKey().lastIndexOf('/') + 1);
        }
        String status = p.getIndexStatus();
        if (status == null || status.isBlank()) {
            status = Integer.valueOf(1).equals(p.getIndexed()) ? "indexed" : "not_added";
        }
        return new PaperView(
                p.getId(), p.getTitle(), fileName, p.getOssKey(),
                p.getSizeBytes() == null ? 0 : p.getSizeBytes(),
                p.getIndexed() == null ? 0 : p.getIndexed(),
                p.getKbEnabled() == null ? 0 : p.getKbEnabled(),
                status, p.getIndexError(), p.getIndexedAt(),
                p.getChunkCount() == null ? 0 : p.getChunkCount(),
                p.getCreatedAt());
    }
}
