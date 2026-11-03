package com.biopilot.file.dto;

import com.biopilot.file.domain.BioFile;
import com.fasterxml.jackson.annotation.JsonProperty;

/** 数据文件列表/上传响应的对外视图。 */
public record FileView(
        @JsonProperty("file_id") String fileId,
        String name,
        long size,
        @JsonProperty("content_type") String contentType,
        @JsonProperty("oss_key") String ossKey,
        String kind,
        long version,
        @JsonProperty("created_at") String createdAt) {

    public static FileView from(BioFile f) {
        return new FileView(f.getId(), f.getName(),
                f.getSizeBytes() == null ? 0 : f.getSizeBytes(),
                f.getContentType(), f.getOssKey(), f.getKind(),
                f.getVersion() == null ? 1 : f.getVersion(), f.getCreatedAt());
    }
}
