package com.biopilot.common.pdf;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.text.PDFTextStripper;
import org.apache.pdfbox.text.TextPosition;

/** 用 PDFBox 读取首页行（含字号/纵坐标）与前几页文本；只服务排版判断与标识符查找。

    不依赖 PyMuPDF；与 RAG 的 Python 解析器并存——Java 侧只需要标题与 DOI/arXiv
    查找所需的少量文本，不重建完整版面块。
*/
public final class PdfTextReader {

    private PdfTextReader() {
    }

    /** 页面上的一行文本。
     *
     * Attributes:
     *     text: 连续空白已折叠的行文本。
     *     size: 行内最大字号。
     *     y: 行首相对页面顶部的纵坐标（向下为正）。
     */
    public record Line(String text, double size, double y) {
    }

    /** 一次读取的结果。
     *
     * Attributes:
     *     firstPageLines: 第一页的全部行（阅读顺序）。
     *     firstPageHeight: 第一页高度。
     *     text: 前若干页的纯文本（用于 DOI/arXiv 查找）。
     */
    public record Snapshot(List<Line> firstPageLines, double firstPageHeight,
                           String text) {
    }

    /** 读取 PDF：首页行 + 前 pages 页文本。
     *
     * Args:
     *     pdf: PDF 字节。
     *     pages: 读取页数上限（从第 1 页起）。
     *
     * Returns:
     *     Snapshot: 首页行、首页高度与前若干页文本。
     *
     * Raises:
     *     IOException: PDF 无法打开或解析。
     */
    public static Snapshot read(byte[] pdf, int pages) throws IOException {
        List<Line> lines = new ArrayList<>();
        StringBuilder text = new StringBuilder();
        try (PDDocument document = Loader.loadPDF(pdf)) {
            if (document.getNumberOfPages() == 0) {
                return new Snapshot(List.of(), 0.0, "");
            }
            double pageHeight = document.getPage(0).getMediaBox().getHeight();
            Collector collector = new Collector(lines, text);
            collector.setSortByPosition(true);
            collector.setStartPage(1);
            collector.setEndPage(Math.max(1, Math.min(pages, document.getNumberOfPages())));
            collector.getText(document);
            return new Snapshot(List.copyOf(lines), pageHeight, text.toString());
        }
    }

    /** PDFTextStripper 子类：按行收集首页行，同时拼出纯文本。 */
    private static final class Collector extends PDFTextStripper {

        private final List<Line> lines;
        private final StringBuilder all;
        private final StringBuilder current = new StringBuilder();
        private double currentSize;
        private double currentY;
        private boolean currentStarted;

        Collector(List<Line> lines, StringBuilder all) throws IOException {
            super();
            this.lines = lines;
            this.all = all;
        }

        @Override
        protected void writeString(String string, List<TextPosition> positions)
                throws IOException {
            if (string == null || string.isEmpty()) {
                return;
            }
            current.append(string);
            all.append(string);
            if (positions != null && !positions.isEmpty()) {
                TextPosition first = positions.get(0);
                if (!currentStarted) {
                    currentY = first.getYDirAdj();
                    currentStarted = true;
                }
                currentSize = Math.max(currentSize, first.getFontSizeInPt());
            }
        }

        @Override
        protected void writeWordSeparator() throws IOException {
            current.append(' ');
            all.append(' ');
        }

        @Override
        protected void writeLineSeparator() throws IOException {
            flushLine();
            all.append('\n');
        }

        @Override
        protected void startPage(org.apache.pdfbox.pdmodel.PDPage page) throws IOException {
            super.startPage(page);
            flushLine();
        }

        private void flushLine() {
            String text = current.toString().replaceAll("\\s+", " ").trim();
            if (!text.isEmpty() && getCurrentPageNo() == 1) {
                lines.add(new Line(text, currentSize, currentY));
            }
            current.setLength(0);
            currentSize = 0.0;
            currentY = 0.0;
            currentStarted = false;
        }
    }
}
