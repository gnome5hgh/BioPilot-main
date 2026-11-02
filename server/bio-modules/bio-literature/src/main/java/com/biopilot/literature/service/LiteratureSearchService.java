package com.biopilot.literature.service;

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
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/** 文献搜索：直查 Europe PMC，返回前端展示与「加入论文库」所需的元数据。 */
@Service
public class LiteratureSearchService {

    private static final Logger log = LoggerFactory.getLogger(LiteratureSearchService.class);

    private final ObjectMapper mapper;
    private final HttpClient client = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    public LiteratureSearchService(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    /** 按关键词检索（最多 10 条）；外部服务失败返回空结果并带 error 文案。 */
    public Map<String, Object> search(String query) {
        if (query == null || query.isBlank()) {
            return Map.of("results", List.of());
        }
        try {
            String url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query="
                    + URLEncoder.encode(query, StandardCharsets.UTF_8)
                    + "&format=json&pageSize=10&resultType=core";
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .timeout(Duration.ofSeconds(15))
                    .GET()
                    .build();
            HttpResponse<String> response = client.send(request,
                    HttpResponse.BodyHandlers.ofString());
            JsonNode rows = mapper.readTree(response.body())
                    .path("resultList").path("result");
            List<Map<String, Object>> results = new ArrayList<>();
            for (JsonNode row : rows) {
                String pmcid = row.path("pmcid").asText("");
                String doi = row.path("doi").asText("");
                String pmid = row.path("pmid").asText("");
                if (pmid.isEmpty()) {
                    pmid = row.path("id").asText("");
                }
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("id", pmid);
                item.put("pmid", pmid);
                item.put("pmcid", pmcid);
                item.put("doi", doi);
                item.put("title", row.path("title").asText(""));
                item.put("authors", row.path("authorString").asText(""));
                item.put("journal", row.path("journalTitle").asText(""));
                item.put("pubdate", row.path("pubYear").asText(""));
                item.put("abstract", row.path("abstractText").asText(""));
                item.put("is_open_access",
                        "Y".equals(row.path("isOpenAccess").asText()) || !pmcid.isEmpty());
                item.put("pdf_url", pmcid.isEmpty()
                        ? "" : "https://europepmc.org/articles/" + pmcid + "?pdf=render");
                results.add(item);
            }
            return Map.of("results", results);
        } catch (Exception e) {
            log.warn("Europe PMC 搜索失败: {}", e.getMessage());
            return Map.of("results", List.of(), "error", String.valueOf(e.getMessage()));
        }
    }
}
