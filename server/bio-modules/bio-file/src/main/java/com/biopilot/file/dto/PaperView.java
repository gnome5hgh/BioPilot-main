package com.biopilot.file.dto;

import com.biopilot.file.domain.BioFile;
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
        @JsonProperty("citation_id") String citationId,
        String authors,
        String year,
        String journal,
        @JsonProperty("index_status") String indexStatus,
        @JsonProperty("index_error") String indexError,
        @JsonProperty("indexed_at") String indexedAt,
        @JsonProperty("chunk_count") int chunkCount,
        @JsonProperty("created_at") String createdAt) {

    public static PaperView from(BioFile p) {
        String fileName = p.getName();
        if (fileName == null || fileName.isBlank()) {
            fileName = p.getOssKey() == null ? ""
                    : p.getOssKey().substring(p.getOssKey().lastIndexOf('/') + 1);
        }
        // 勾选状态是「是否在知识库」的唯一真相。索引列由另一个进程写，跨栈通知
        // 丢失或并发移出时会留下旧值；不归一化就会在文件管理里显示「已就绪」，
        // 而知识库清单里根本没有这篇论文。未勾选一律按未加入展示。
        boolean inKb = Integer.valueOf(1).equals(p.getKbEnabled());
        String status;
        int chunks;
        if (!inKb) {
            status = "not_added";
            chunks = 0;
        } else {
            status = p.getIndexStatus();
            if (status == null || status.isBlank()) {
                status = Integer.valueOf(1).equals(p.getIndexed()) ? "indexed" : "queued";
            }
            chunks = p.getChunkCount() == null ? 0 : p.getChunkCount();
        }
        return new PaperView(
                p.getId(), p.getTitle(), fileName, p.getOssKey(),
                p.getSizeBytes() == null ? 0 : p.getSizeBytes(),
                p.getIndexed() == null ? 0 : p.getIndexed(),
                p.getKbEnabled() == null ? 0 : p.getKbEnabled(),
                p.getCitationId(),
                p.getAuthors() == null ? "" : p.getAuthors(),
                p.getYear() == null ? "" : p.getYear(),
                p.getJournal() == null ? "" : p.getJournal(),
                status, p.getIndexError(), p.getIndexedAt(),
                chunks, p.getCreatedAt());
    }
}
