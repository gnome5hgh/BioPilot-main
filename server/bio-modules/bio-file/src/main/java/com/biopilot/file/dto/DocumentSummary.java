package com.biopilot.file.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/** 文档列表项（不含正文）。 */
public record DocumentSummary(
        String id,
        String name,
        @JsonProperty("updated_at") String updatedAt) {
}
