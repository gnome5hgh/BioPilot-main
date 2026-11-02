package com.biopilot.common.pdf;

import org.springframework.stereotype.Component;

/** PDF 元数据提取门面：标题本地提取，作者/年份/期刊经标识符查外部书目。

    标题只做本地版面判断（不联网）；书目查询失败只留空。平台在上传时需要标题
    先落库（知识库索引要从 DB 取标题），所以 ``extractTitle`` 与
    ``extract`` 分开：前者快且无网络，后者供「加入引用库」使用。
*/
@Component
public class PdfMetadataExtractor {

    private final PdfTitleExtractor titles = new PdfTitleExtractor();
    private final PdfIdentifierExtractor identifiers = new PdfIdentifierExtractor();
    private final BibliographyClient bibliography = new BibliographyClient();

    /** 只提取标题（本地、无网络）。
     *
     * Args:
     *     pdf: PDF 字节。
     *
     * Returns:
     *     str: 标题；提取失败为空串。
     */
    public String extractTitle(byte[] pdf) {
        return titles.extract(pdf);
    }

    /** 提取完整书目：标题优先本地，作者/年份/期刊按 DOI/arXiv 查询补齐。
     *
     * Args:
     *     pdf: PDF 字节。
     *
     * Returns:
     *     PaperMeta: 书目字段；取不到的字段为空串。
     */
    public PaperMeta extract(byte[] pdf) {
        String title = titles.extract(pdf);
        PdfIdentifierExtractor.Identifier identifier = identifiers.extract(pdf);
        PaperMeta remote = identifier.doi().isBlank()
                ? bibliography.byArxiv(identifier.arxiv())
                : bibliography.byDoi(identifier.doi());
        PaperMeta local = new PaperMeta(title, "", "", "", identifier.doi(), "article");
        return local.merge(remote);
    }
}
