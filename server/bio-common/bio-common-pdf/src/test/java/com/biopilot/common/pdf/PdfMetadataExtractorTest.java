package com.biopilot.common.pdf;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.common.PDRectangle;
import org.apache.pdfbox.pdmodel.font.PDType1Font;
import org.apache.pdfbox.pdmodel.font.Standard14Fonts;
import org.junit.jupiter.api.Test;

/** 标题/标识符提取的口径测试：元数据优先、垃圾标题不退化、字号启发式、宁空勿错。 */
class PdfMetadataExtractorTest {

    private final PdfMetadataExtractor extractor = new PdfMetadataExtractor();

    @Test
    void metadataTitleWins() throws IOException {
        byte[] pdf = pdf("Real Metadata Title", "Body text for the first page.", false);
        assertThat(extractor.extractTitle(pdf)).isEqualTo("Real Metadata Title");
    }

    @Test
    void junkMetadataTitleMeansEmptyNotHeuristic() throws IOException {
        // 元数据标题是工具生成的垃圾：宁可空着，也不退回版面启发式
        byte[] pdf = pdf("Microsoft Word - main.pdf", "Body text for the first page.", true);
        assertThat(extractor.extractTitle(pdf)).isEmpty();
    }

    @Test
    void heuristicFindsLargestTopLine() throws IOException {
        byte[] pdf = pdf("", "Body text for the first page.", true);
        assertThat(extractor.extractTitle(pdf)).isEqualTo("Layout Guessed Paper Title");
    }

    @Test
    void bodySizedTextIsNeverATitle() throws IOException {
        byte[] pdf = pdf("", "Body text for the first page.", false);
        assertThat(extractor.extractTitle(pdf)).isEmpty();
    }

    @Test
    void findsDoiAndArxiv() throws IOException {
        byte[] pdf = pdf("", "See doi:10.1234/abcd.5678 and arXiv:2401.01234v2.", true);
        PdfIdentifierExtractor.Identifier id = new PdfIdentifierExtractor().extract(pdf);
        assertThat(id.doi()).isEqualTo("10.1234/abcd.5678");
        assertThat(id.arxiv()).isEqualTo("2401.01234");
    }

    @Test
    void titleNormalizerIgnoresPunctuationCaseAndSpaces() {
        assertThat(com.biopilot.common.core.text.TitleNormalizer.normalize(
                "CircRNA:  A  Survey!"))
                .isEqualTo("circrnaasurvey");
    }

    /** 生成一页 PDF；bigTitle=true 时在页首放一个 20pt 标题行。 */
    private byte[] pdf(String metadataTitle, String body, boolean bigTitle) throws IOException {
        try (PDDocument document = new PDDocument()) {
            PDPage page = new PDPage(PDRectangle.A4);
            document.addPage(page);
            try (PDPageContentStream stream = new PDPageContentStream(document, page)) {
                if (bigTitle) {
                    stream.beginText();
                    stream.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA_BOLD), 20);
                    stream.newLineAtOffset(72, 740);
                    stream.showText("Layout Guessed Paper Title");
                    stream.endText();
                }
                stream.beginText();
                stream.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 10);
                stream.newLineAtOffset(72, 700);
                for (int i = 0; i < 12; i++) {
                    stream.showText(body);
                    stream.newLineAtOffset(0, -14);
                }
                stream.endText();
            }
            if (metadataTitle != null && !metadataTitle.isEmpty()) {
                document.getDocumentInformation().setTitle(metadataTitle);
            }
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            document.save(out);
            return out.toByteArray();
        }
    }
}
