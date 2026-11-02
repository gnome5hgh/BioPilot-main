package com.biopilot.citation.service;

import java.util.Locale;
import java.util.Set;

/** 引用键生成：{一作姓氏}{年份}{短标题}，对齐手写文献库的可读 key 约定。 */
public final class CitationKeyGenerator {

    /** 短标题生成时跳过的首词停用词。 */
    private static final Set<String> STOPWORDS = Set.of(
            "the", "a", "an", "of", "in", "for", "and", "on", "to", "with",
            "toward", "towards", "from", "by", "at", "using", "via");

    private CitationKeyGenerator() {
    }

    /** 生成 key（小写）。
     *
     * Args:
     *     title: 论文标题。
     *     authors: BibTeX 作者串（取第一作者姓氏）。
     *     year: 年份。
     *
     * Returns:
     *     str: 形如 ``smith2024attention`` 的 key。
     */
    public static String generate(String title, String authors, String year) {
        String first = "";
        if (authors != null && !authors.isBlank()) {
            first = authors.trim().split("[,\\s]+")[0].toLowerCase(Locale.ROOT);
        }
        return first + (year == null ? "" : year.trim()) + shortTitle(title);
    }

    /** 取首个非停用词作短标题；全为停用词时取首词，无词时用 paper。 */
    static String shortTitle(String title) {
        String[] words = (title == null ? "" : title)
                .toLowerCase(Locale.ROOT).split("[^a-z0-9]+");
        String first = null;
        for (String word : words) {
            if (word.isEmpty()) {
                continue;
            }
            if (first == null) {
                first = word;
            }
            if (!STOPWORDS.contains(word)) {
                return word;
            }
        }
        return first == null ? "paper" : first;
    }
}
