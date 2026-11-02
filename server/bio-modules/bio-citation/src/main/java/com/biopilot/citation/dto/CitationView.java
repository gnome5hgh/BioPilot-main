package com.biopilot.citation.dto;

import com.biopilot.citation.domain.BioCitation;
import com.fasterxml.jackson.annotation.JsonProperty;

/** 引用条目的对外视图（字段与前端既有契约对齐）。 */
public record CitationView(
        String key,
        @JsonProperty("entry_type") String entryType,
        String title,
        String authors,
        String year,
        String journal,
        String volume,
        String pages,
        String doi,
        String source) {

    public static CitationView from(BioCitation row) {
        return new CitationView(
                row.getCiteKey(), row.getEntryType(), row.getTitle(),
                row.getAuthors() == null ? "" : row.getAuthors(),
                row.getYear() == null ? "" : row.getYear(),
                row.getJournal() == null ? "" : row.getJournal(),
                row.getVolume() == null ? "" : row.getVolume(),
                row.getPages() == null ? "" : row.getPages(),
                row.getDoi() == null ? "" : row.getDoi(),
                row.getSource());
    }
}
