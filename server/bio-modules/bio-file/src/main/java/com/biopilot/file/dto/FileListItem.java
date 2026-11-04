package com.biopilot.file.dto;

import com.biopilot.file.domain.BioFile;
import com.fasterxml.jackson.annotation.JsonProperty;

/** 数据文件列表项：字段名与前端既有契约一致（id / size_bytes）。 */
public record FileListItem(
        String id,
        String name,
        @JsonProperty("size_bytes") long sizeBytes,
        @JsonProperty("content_type") String contentType,
        @JsonProperty("oss_key") String ossKey,
        String kind,
        @JsonProperty("source") String source,
        long version,
        @JsonProperty("created_at") String createdAt) {

    public static FileListItem from(BioFile f) {
        return new FileListItem(f.getId(), f.getName(),
                f.getSizeBytes() == null ? 0 : f.getSizeBytes(),
                f.getContentType(), f.getOssKey(), f.getKind(), f.getSource(),
                f.getVersion() == null ? 1 : f.getVersion(), f.getCreatedAt());
    }
}
