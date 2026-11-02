package com.biopilot.common.pdf;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Pattern;

/** 从 PDF 提取论文标题（元数据标题优先，其次首页字号启发式）。

    判据与 Python 侧``pdf_extract._title_of``同口径：元数据里有标题时由形态判据
    定生死（判为垃圾也不退回启发式，宁可空着）；没有元数据标题才按首页版面试。
    空标题是安全降级，错标题会污染文件管理、引用库与检索块前缀。
*/
public final class PdfTitleExtractor {

    /** 标题最短字符数：短于此的行几乎不可能是论文标题。 */
    private static final int TITLE_MIN_CHARS = 8;
    /** 标题字号至少是正文字号的倍数。 */
    private static final double HEADING_SIZE_RATIO = 1.10;
    /** 标题只出现在页面上部：超过页面高度的这个比例不做候选。 */
    private static final double TOP_REGION_RATIO = 0.4;

    private static final String[] BAD_SUFFIXES =
            {".pdf", ".dvi", ".tex", ".docx", ".doc", ".ps", ".html"};

    private static final Pattern[] JUNK = {
            Pattern.compile("^untitled$", Pattern.CASE_INSENSITIVE),
            Pattern.compile("^microsoft word\\s*[-–—]\\s*", Pattern.CASE_INSENSITIVE),
            Pattern.compile("^\\d+$"),
            Pattern.compile("^[A-Z]{2,}[-_][A-Z0-9]{3,}\\s+\\d+\\.{2,}\\d+$"),
            Pattern.compile("^arxiv\\s*:", Pattern.CASE_INSENSITIVE),
            Pattern.compile("^(?:journal|proceedings|volume|vol\\.|issue)\\b",
                    Pattern.CASE_INSENSITIVE),
            Pattern.compile("^https?://", Pattern.CASE_INSENSITIVE),
    };

    private static final String[] WATERMARKS = {
            "journal pre-proof", "accepted manuscript", "this is a preprint",
            "downloaded from", "all rights reserved", "see discussions",
            "cc-by", "cc by", "©",
    };

    private static final Pattern AUTHOR_MARK =
            Pattern.compile("[∗*†‡§]|\\biD\\b|\\bdoi\\b|[\\u00b9\\u00b2\\u00b3\\u2074-\\u2079]");

    /** 读取 PDF 并返回标题；解析失败返回空串（不阻断上传）。
     *
     * Args:
     *     pdf: PDF 字节。
     *
     * Returns:
     *     str: 标题；拿不准时为空串。
     */
    public String extract(byte[] pdf) {
        try {
            PdfTextReader.Snapshot snapshot = PdfTextReader.read(pdf, 1);
            String metadata = metadataTitle(pdf);
            if (!metadata.isBlank()) {
                return looksLikeTitle(metadata) ? metadata : "";
            }
            return heuristicTitle(snapshot.firstPageLines(), snapshot.firstPageHeight());
        } catch (IOException | RuntimeException e) {
            return "";
        }
    }

    /** 读 PDF 元数据标题（连续空白折叠）；读不到返回空串。 */
    private String metadataTitle(byte[] pdf) {
        try (org.apache.pdfbox.pdmodel.PDDocument document =
                     org.apache.pdfbox.Loader.loadPDF(pdf)) {
            String raw = document.getDocumentInformation().getTitle();
            return raw == null ? "" : raw.replaceAll("\\s+", " ").trim();
        } catch (IOException | RuntimeException e) {
            return "";
        }
    }

    /** 从首页版面猜标题：字号最大、位置最靠上的连续同字号行组，逐组过形态判据。 */
    private String heuristicTitle(List<PdfTextReader.Line> lines, double pageHeight) {
        if (lines.isEmpty() || pageHeight <= 0) {
            return "";
        }
        double bodySize = dominantSize(lines);
        List<List<PdfTextReader.Line>> groups = new ArrayList<>();
        for (PdfTextReader.Line line : lines) {
            String text = line.text();
            if (text.length() < TITLE_MIN_CHARS) {
                continue;
            }
            if (line.y() > pageHeight * TOP_REGION_RATIO) {
                continue;
            }
            if (bodySize > 0 && line.size() <= bodySize * HEADING_SIZE_RATIO) {
                continue;
            }
            if (!groups.isEmpty()) {
                PdfTextReader.Line last = groups.get(groups.size() - 1)
                        .get(groups.get(groups.size() - 1).size() - 1);
                boolean sameSize = Math.abs(last.size() - line.size()) <= 0.5;
                boolean adjacent = line.y() - last.y() <= 2.0 * Math.max(line.size(), 1.0);
                if (sameSize && adjacent) {
                    groups.get(groups.size() - 1).add(line);
                    continue;
                }
            }
            List<PdfTextReader.Line> group = new ArrayList<>();
            group.add(line);
            groups.add(group);
        }
        groups.sort(Comparator
                .comparingDouble((List<PdfTextReader.Line> g) -> -round1(g.get(0).size()))
                .thenComparingDouble(g -> g.get(0).y()));
        for (List<PdfTextReader.Line> group : groups) {
            StringBuilder candidate = new StringBuilder();
            for (PdfTextReader.Line line : group) {
                if (candidate.length() > 0) {
                    candidate.append(' ');
                }
                candidate.append(line.text());
            }
            String text = candidate.toString().trim();
            if (looksLikeTitle(text)) {
                return text;
            }
        }
        return "";
    }

    /** 正文字号：按字符量加权投票（与 Python 同口径）。 */
    private double dominantSize(List<PdfTextReader.Line> lines) {
        Map<Double, Integer> weight = new LinkedHashMap<>();
        for (PdfTextReader.Line line : lines) {
            if (line.size() <= 0) {
                continue;
            }
            double key = round1(line.size());
            weight.merge(key, line.text().length(), Integer::sum);
        }
        return weight.entrySet().stream()
                .max(Map.Entry.comparingByValue())
                .map(Map.Entry::getKey)
                .orElse(0.0);
    }

    /** 形态判据：只回答「明确不是什么」，过了不代表一定是标题。 */
    static boolean looksLikeTitle(String text) {
        String candidate = text == null ? "" : text.replaceAll("\\s+", " ").trim();
        if (candidate.length() < TITLE_MIN_CHARS) {
            return false;
        }
        String lower = candidate.toLowerCase(Locale.ROOT);
        for (String suffix : BAD_SUFFIXES) {
            if (lower.endsWith(suffix)) {
                return false;
            }
        }
        if (candidate.contains("/") || candidate.contains("\\")) {
            return false;
        }
        for (Pattern pattern : JUNK) {
            if (pattern.matcher(candidate).find()) {
                return false;
            }
        }
        for (String mark : WATERMARKS) {
            if (lower.contains(mark)) {
                return false;
            }
        }
        return !looksLikeAuthorLine(candidate);
    }

    /** 作者行：带姓名标记且是逗号分隔的多个短人名串。 */
    private static boolean looksLikeAuthorLine(String text) {
        if (!AUTHOR_MARK.matcher(text).find()) {
            return false;
        }
        String[] parts = text.split(",");
        List<String> names = new ArrayList<>();
        for (String part : parts) {
            String value = part.trim();
            if (!value.isEmpty()) {
                names.add(value);
            }
        }
        if (names.size() < 2) {
            return false;
        }
        for (String name : names) {
            if (!Character.isUpperCase(name.charAt(0)) || name.split("\\s+").length > 5) {
                return false;
            }
        }
        return true;
    }

    private static double round1(double value) {
        return Math.round(value * 10.0) / 10.0;
    }
}
