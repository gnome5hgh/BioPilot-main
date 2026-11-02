package com.biopilot.literature.service.provider;

import com.biopilot.literature.domain.PaperCandidate;
import com.biopilot.literature.domain.SearchQuery;
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
import org.springframework.stereotype.Component;

/**
 * Europe PMC 检索源：直查 Europe PMC REST，作为平台内置兜底。
 *
 * <p>它能覆盖生物医学文献且无需密钥；外部 MCP 源不可用时，聚合服务仍能返回结果。
 * 年份过滤拼进 Europe PMC 自己的查询语法（{@code PUB_YEAR:[from TO to]}），不当作
 * 普通关键词，避免过滤失效。</p>
 */
@Component
public class EuropePmcProvider implements LiteratureProvider {

    private static final String ENDPOINT =
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search";

    private final ObjectMapper mapper;
    private final HttpClient client = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    public EuropePmcProvider(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public String name() {
        return "europepmc";
    }

    @Override
    public List<PaperCandidate> search(SearchQuery query) throws Exception {
        String url = ENDPOINT
                + "?query=" + URLEncoder.encode(withYearFilter(query), StandardCharsets.UTF_8)
                + "&format=json&pageSize=" + query.limit() + "&resultType=core";
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(15))
                .GET()
                .build();
        HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() >= 300) {
            throw new IllegalStateException("Europe PMC HTTP " + response.statusCode());
        }
        JsonNode rows = mapper.readTree(response.body()).path("resultList").path("result");
        List<PaperCandidate> results = new ArrayList<>();
        for (JsonNode row : rows) {
            results.add(toCandidate(row));
        }
        return results;
    }

    /** 把年份条件拼进 Europe PMC 查询语法，而不是让检索源当普通词模糊匹配。 */
    private static String withYearFilter(SearchQuery query) {
        if (query.yearFrom() == null && query.yearTo() == null) {
            return query.query();
        }
        String from = query.yearFrom() == null ? "*" : String.valueOf(query.yearFrom());
        String to = query.yearTo() == null ? "*" : String.valueOf(query.yearTo());
        return "(" + query.query() + ") AND PUB_YEAR:[" + from + " TO " + to + "]";
    }

    private static PaperCandidate toCandidate(JsonNode row) {
        String pmid = row.path("pmid").asText("");
        String pmcid = row.path("pmcid").asText("");
        String doi = row.path("doi").asText("");
        String fallbackId = row.path("id").asText("");
        String id = !pmid.isBlank() ? pmid : (!pmcid.isBlank() ? pmcid : fallbackId);
        String source = row.path("source").asText("MED");
        boolean openAccess = "Y".equals(row.path("isOpenAccess").asText()) || !pmcid.isBlank();
        String pdfUrl = pmcid.isBlank()
                ? "" : "https://europepmc.org/articles/" + pmcid + "?pdf=render";
        String detailUrl = id.isBlank() ? "" : "https://europepmc.org/article/" + source + "/" + id;
        return new PaperCandidate(
                id,
                row.path("title").asText(""),
                row.path("authorString").asText(""),
                row.path("pubYear").asText(""),
                row.path("journalTitle").asText(""),
                doi,
                pmid,
                pmcid,
                row.path("abstractText").asText(""),
                openAccess,
                pdfUrl,
                detailUrl,
                "europepmc",
                row.path("citedByCount").asInt(0));
    }
}
