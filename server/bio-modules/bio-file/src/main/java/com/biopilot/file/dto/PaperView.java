package com.biopilot.file.dto;

import com.biopilot.file.domain.BioFile;
import com.biopilot.file.domain.PaperIndexStatus;
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

    /** 新入库的论文：状态行尚未产生，按勾选给出初始展示态。 */
    public static PaperView from(BioFile p) {
        return from(p, null);
    }

    /**
     * 从行与引擎状态行合成视图。
     *
     * <p>勾选状态是「是否在知识库」的唯一真相：未勾选一律按未加入展示，状态行
     * 残留的 indexed/chunk_count 不外露。已勾选但引擎还没有状态行时按 queued
     * 展示（引擎下一轮会补 queued）。</p>
     *
     * @param p      bio_file 行（身份/文件/书目/勾选列）。
     * @param status 引擎索引状态行；null 表示尚无状态行。
     */
    public static PaperView from(BioFile p, PaperIndexStatus status) {
        String fileName = p.getName();
        if (fileName == null || fileName.isBlank()) {
            fileName = p.getOssKey() == null ? ""
                    : p.getOssKey().substring(p.getOssKey().lastIndexOf('/') + 1);
        }
        boolean inKb = Integer.valueOf(1).equals(p.getKbEnabled());
        String viewStatus;
        int chunks;
        int indexed;
        String indexError = null;
        String indexedAt = null;
        if (!inKb) {
            viewStatus = "not_added";
            chunks = 0;
            indexed = 0;
        } else if (status == null) {
            viewStatus = "queued";
            chunks = 0;
            indexed = 0;
        } else {
            viewStatus = status.getIndexStatus();
            if (viewStatus == null || viewStatus.isBlank()) {
                viewStatus = Integer.valueOf(1).equals(status.getIndexed())
                        ? "indexed" : "queued";
            }
            chunks = status.getChunkCount() == null ? 0 : status.getChunkCount();
            indexed = status.getIndexed() == null ? 0 : status.getIndexed();
            indexError = status.getIndexError();
            indexedAt = status.getIndexedAt();
        }
        return new PaperView(
                p.getId(), p.getTitle(), fileName, p.getOssKey(),
                p.getSizeBytes() == null ? 0 : p.getSizeBytes(),
                indexed,
                p.getKbEnabled() == null ? 0 : p.getKbEnabled(),
                p.getCitationId(),
                p.getAuthors() == null ? "" : p.getAuthors(),
                p.getYear() == null ? "" : p.getYear(),
                p.getJournal() == null ? "" : p.getJournal(),
                viewStatus, indexError, indexedAt,
                chunks, p.getCreatedAt());
    }
}
