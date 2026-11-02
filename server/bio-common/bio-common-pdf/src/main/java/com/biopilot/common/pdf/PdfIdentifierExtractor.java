package com.biopilot.common.pdf;

import java.io.IOException;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** 从 PDF 文本里找 DOI / arXiv 标识符，供书目查询使用。

    只扫描前几页与文档元数据，不做全文扫描；找不到就留空，不猜测。
*/
public final class PdfIdentifierExtractor {

    private static final Pattern DOI_PATTERN =
            Pattern.compile("10\\.\\d{4,9}/[^\\s\"<>]+");
    private static final Pattern ARXIV_PATTERN =
            Pattern.compile("arXiv\\s*:\\s*(\\d{4}\\.\\d{4,5})(?:v\\d+)?",
                    Pattern.CASE_INSENSITIVE);
    private static final Pattern ARXIV_URL_PATTERN =
            Pattern.compile("arxiv\\.org/(?:abs|pdf)/(\\d{4}\\.\\d{4,5})",
                    Pattern.CASE_INSENSITIVE);
    private static final Pattern TRAILING = Pattern.compile("[.,;:)\\]}]+$");

    /** 标识符集合；可能都为空。
     *
     * Attributes:
     *     doi: DOI（不带前缀 URL）。
     *     arxiv: arXiv id（如 2401.01234）。
     */
    public record Identifier(String doi, String arxiv) {
        /** 两者都没有。 */
        public static final Identifier EMPTY = new Identifier("", "");
    }

    /** 从 PDF 中提取标识符。
     *
     * Args:
     *     pdf: PDF 字节。
     *
     * Returns:
     *     Identifier: 找到的 DOI / arXiv；解析失败返回空。
     */
    public Identifier extract(byte[] pdf) {
        try {
            PdfTextReader.Snapshot snapshot = PdfTextReader.read(pdf, 3);
            String haystack = snapshot.text() + " " + metadata(pdf);
            return new Identifier(findDoi(haystack), findArxiv(haystack));
        } catch (IOException | RuntimeException e) {
            return Identifier.EMPTY;
        }
    }

    private String metadata(byte[] pdf) {
        try (org.apache.pdfbox.pdmodel.PDDocument document =
                     org.apache.pdfbox.Loader.loadPDF(pdf)) {
            var info = document.getDocumentInformation();
            return String.join(" ",
                    nullToEmpty(info.getTitle()), nullToEmpty(info.getSubject()),
                    nullToEmpty(info.getKeywords()), nullToEmpty(info.getAuthor()));
        } catch (IOException | RuntimeException e) {
            return "";
        }
    }

    private String findDoi(String text) {
        Matcher matcher = DOI_PATTERN.matcher(text);
        if (!matcher.find()) {
            return "";
        }
        return TRAILING.matcher(matcher.group()).replaceAll("");
    }

    private String findArxiv(String text) {
        Matcher matcher = ARXIV_PATTERN.matcher(text);
        if (matcher.find()) {
            return matcher.group(1);
        }
        Matcher url = ARXIV_URL_PATTERN.matcher(text);
        return url.find() ? url.group(1) : "";
    }

    private static String nullToEmpty(String value) {
        return value == null ? "" : value;
    }
}
