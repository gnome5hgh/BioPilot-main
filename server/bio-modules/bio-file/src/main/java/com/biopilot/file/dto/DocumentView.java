package com.biopilot.file.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/** 文档读接口的对外视图；version 用于保存时的乐观锁。 */
public record DocumentView(
        String id,
        String name,
        String content,
        long version,
        @JsonProperty("updated_at") String updatedAt) {
}
