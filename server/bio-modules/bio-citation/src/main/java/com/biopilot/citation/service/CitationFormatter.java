package com.biopilot.citation.service;

import com.biopilot.citation.domain.BioCitation;
import java.util.List;

/** 引用渲染：author-year / numbered / gbt7714 / bibtex。 */
public final class CitationFormatter {

    private CitationFormatter() {
    }

    /** 按样式渲染条目。
     *
     * Args:
     *     rows: 引用条目（按调用方给定顺序）。
     *     style: author-year / numbered / gbt7714 / bibtex。
     *
     * Returns:
     *     str: 渲染后的参考文献文本。
     */
    public static String format(List<BioCitation> rows, String style) {
        if ("bibtex".equals(style)) {
            StringBuilder out = new StringBuilder();
            for (BioCitation row : rows) {
                if (out.length() > 0) {
                    out.append("\n\n");
                }
                out.append(bibtex(row));
            }
            return out.toString();
        }
        if ("numbered".equals(style)) {
            StringBuilder out = new StringBuilder();
            for (int i = 0; i < rows.size(); i++) {
                BioCitation row = rows.get(i);
                if (out.length() > 0) {
                    out.append('\n');
                }
                out.append('[').append(i + 1).append("] ")
                        .append(nvl(row.getAuthors())).append(". ")
                        .append(nvl(row.getTitle())).append(". ")
                        .append(nvl(row.getJournal())).append(", ")
                        .append(nvl(row.getYear())).append('.');
            }
            return out.toString();
        }
        if ("gbt7714".equals(style)) {
            StringBuilder out = new StringBuilder();
            for (BioCitation row : rows) {
                if (out.length() > 0) {
                    out.append('\n');
                }
                String first = firstAuthor(row.getAuthors());
                out.append(first).append(" 等. ")
                        .append(nvl(row.getTitle())).append("[J]. ")
                        .append(nvl(row.getJournal())).append(", ")
                        .append(nvl(row.getYear())).append(", ")
                        .append(nvl(row.getVolume())).append(": ")
                        .append(nvl(row.getPages())).append('.');
            }
            return out.toString();
        }
        StringBuilder out = new StringBuilder();
        for (BioCitation row : rows) {
            if (out.length() > 0) {
                out.append('\n');
            }
            String first = firstAuthor(row.getAuthors());
            String suffix = row.getAuthors() != null && row.getAuthors().contains(" and ")
                    ? " et al." : "";
            out.append('(').append(first).append(suffix).append(", ")
                    .append(nvl(row.getYear())).append(") ")
                    .append(nvl(row.getTitle())).append('.');
        }
        return out.toString();
    }

    /** 渲染单条 BibTeX（只输出非空字段）。 */
    private static String bibtex(BioCitation row) {
        StringBuilder out = new StringBuilder();
        out.append('@').append(nvl(row.getEntryType())).append('{')
                .append(nvl(row.getCiteKey())).append(",\n");
        appendField(out, "author", row.getAuthors());
        appendField(out, "title", row.getTitle());
        appendField(out, "journal", row.getJournal());
        appendField(out, "year", row.getYear());
        appendField(out, "volume", row.getVolume());
        appendField(out, "pages", row.getPages());
        appendField(out, "doi", row.getDoi());
        if (out.charAt(out.length() - 1) == ',') {
            out.setLength(out.length() - 1);
        }
        out.append("\n}");
        return out.toString();
    }

    private static void appendField(StringBuilder out, String name, String value) {
        if (value != null && !value.isBlank()) {
            out.append("  ").append(name).append(" = {").append(value).append("},\n");
        }
    }

    private static String firstAuthor(String authors) {
        if (authors == null || authors.isBlank()) {
            return "";
        }
        String first = authors.split(" and ")[0];
        return first.split(",")[0];
    }

    private static String nvl(String value) {
        return value == null ? "" : value;
    }
}
