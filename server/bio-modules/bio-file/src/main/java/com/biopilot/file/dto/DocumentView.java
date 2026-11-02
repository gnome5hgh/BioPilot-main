package com.biopilot.file.dto;

import com.biopilot.file.domain.BioDocument;
import com.fasterxml.jackson.annotation.JsonProperty;

/** 文档读接口的对外视图。 */
public record DocumentView(
        String id,
        String name,
        String content,
        @JsonProperty("updated_at") String updatedAt) {

    public static DocumentView from(BioDocument d) {
        return new DocumentView(d.getId(), d.getName(), d.getContent(), d.getUpdatedAt());
    }
}
