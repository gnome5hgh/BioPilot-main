package com.biopilot.common.pdf;

/** 从 PDF 提取出的书目元数据；取不到的字段一律空串，绝不用文件名顶替。

    Attributes:
        title: 论文标题（解析器出口；宁空勿错）。
        authors: BibTeX 形式作者串（``Last, First and Last, First``）。
        year: 四位年份。
        journal: 期刊或会议名。
        doi: DOI（可能为空）。
        entryType: BibTeX 条目类型（article/inproceedings/...）。
*/
public record PaperMeta(String title, String authors, String year, String journal,
                        String doi, String entryType) {

    /** 空结果：所有字段为空，类型按 article。 */
    public static final PaperMeta EMPTY =
            new PaperMeta("", "", "", "", "", "article");

    /** 用派生字段补齐空值，返回新对象（不覆盖已有非空字段）。
     *
     * Args:
     *     fallback: 后备书目（通常来自 CrossRef/arXiv）。
     *
     * Returns:
     *     PaperMeta: 当前对象优先、后备补空的合并结果。
     */
    public PaperMeta merge(PaperMeta fallback) {
        if (fallback == null) {
            return this;
        }
        return new PaperMeta(
                blank(title) ? fallback.title : title,
                blank(authors) ? fallback.authors : authors,
                blank(year) ? fallback.year : year,
                blank(journal) ? fallback.journal : journal,
                blank(doi) ? fallback.doi : doi,
                blank(entryType) ? fallback.entryType : entryType);
    }

    private static boolean blank(String value) {
        return value == null || value.isBlank();
    }
}
