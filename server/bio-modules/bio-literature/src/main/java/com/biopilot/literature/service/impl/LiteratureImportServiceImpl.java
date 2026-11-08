package com.biopilot.literature.service.impl;

import com.biopilot.literature.service.LiteratureImportService;

import com.biopilot.file.dto.PaperView;
import com.biopilot.file.service.PaperService;
import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.common.net.SafePdfFetcher;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;

/** 文献导入：Europe PMC/OpenAlex 结果 → 开放获取 PDF → 论文库（bio_file + OSS）。 */
@Service
public class LiteratureImportServiceImpl implements LiteratureImportService {

    private final PaperService papers;
    private final ObjectMapper mapper;
    private final HttpClient client = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    public LiteratureImportServiceImpl(PaperService papers, ObjectMapper mapper) {
        this.papers = papers;
        this.mapper = mapper;
    }

    public Map<String, Object> importPaper(long userId, Map<String, Object> body) {
        String title = String.valueOf(body.getOrDefault("title", "")).trim();
        if (title.isEmpty()) {
            throw new ServiceException(422, "文献标题为空，无法加入论文库");
        }
        String name = sanitizeName(title.length() > 120 ? title.substring(0, 120) : title) + ".pdf";
        papers.assertNameAvailable(userId, name);

        List<String> candidates = new ArrayList<>();
        String doi = String.valueOf(body.getOrDefault("doi", "")).trim();
        if (!doi.isEmpty()) {
            String resolved = resolveOpenAccess(doi);
            if (!resolved.isBlank()) {
                candidates.add(resolved);
            }
        }
        String pdfUrl = String.valueOf(body.getOrDefault("pdf_url", "")).trim();
        if (!pdfUrl.isEmpty() && !candidates.contains(pdfUrl)) {
            candidates.add(pdfUrl);
        }
        if (candidates.isEmpty()) {
            throw new ServiceException(422, "没有找到开放获取全文，请手动上传 PDF 或复制引用");
        }

        byte[] data = null;
        String lastError = "";
        for (String url : candidates) {
            try {
                data = SafePdfFetcher.fetch(url);
                if (data != null && data.length > 0) {
                    break;
                }
            } catch (Exception e) {
                lastError = e.getMessage();
            }
        }
        if (data == null || data.length == 0) {
            throw new ServiceException(422,
                    "全文下载失败：" + (lastError.isBlank() ? "下载到的全文为空" : lastError));
        }

        // Europe PMC 的搜索结果已带作者/期刊/年份，直接落库，避免再从 PDF 提取
        String authors = String.valueOf(body.getOrDefault("authors", "")).trim();
        String journal = String.valueOf(body.getOrDefault("journal", "")).trim();
        String year = String.valueOf(body.getOrDefault("pubdate", "")).trim();
        PaperView paper = papers.ingest(userId, title, authors, year, journal, name, data,
                "application/pdf", false);
        return Map.of("status", "ok", "paper_id", paper.id(), "file_name", paper.fileName());
    }

    /** 按 DOI 查 OpenAlex 的开放获取 PDF 地址；查不到按无开放获取处理。 */
    private String resolveOpenAccess(String doi) {
        try {
            String query = URLEncoder.encode(doi, StandardCharsets.UTF_8);
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create("https://api.openalex.org/works?filter=doi:"
                            + query + "&per-page=1"))
                    .timeout(Duration.ofSeconds(10))
                    .GET()
                    .build();
            HttpResponse<String> response = client.send(request,
                    HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() >= 300) {
                return "";
            }
            JsonNode results = mapper.readTree(response.body()).path("results");
            if (!results.isArray() || results.isEmpty()) {
                return "";
            }
            JsonNode row = results.get(0);
            for (String key : new String[]{"best_oa_location", "primary_location"}) {
                String pdf = row.path(key).path("pdf_url").asText("");
                if (!pdf.isBlank()) {
                    return pdf;
                }
            }
        } catch (Exception ignored) {
            // 查询失败按「无开放获取」处理，交给候选链接/明确报错
        }
        return "";
    }

    private String sanitizeName(String name) {
        String base = name.replaceAll("[\\\\/:*?\"<>|\\x00-\\x1f]", "_").trim();
        return base.isBlank() ? "paper" : base;
    }
}
