package com.biopilot.catalog.dto;

import com.biopilot.catalog.domain.UploadedFile;
import com.fasterxml.jackson.annotation.JsonProperty;

/** 数据文件列表项：字段名与前端既有契约一致（id / size_bytes）。 */
public record FileListItem(
        String id,
        String name,
        @JsonProperty("size_bytes") long sizeBytes,
        @JsonProperty("content_type") String contentType,
        @JsonProperty("oss_key") String ossKey,
        @JsonProperty("created_at") String createdAt) {

    public static FileListItem from(UploadedFile f) {
        return new FileListItem(f.getId(), f.getName(),
                f.getSizeBytes() == null ? 0 : f.getSizeBytes(),
                f.getContentType(), f.getOssKey(), f.getCreatedAt());
    }
}
