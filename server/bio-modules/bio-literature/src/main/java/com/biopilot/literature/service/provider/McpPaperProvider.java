package com.biopilot.literature.service.provider;

import com.biopilot.common.mcp.McpClientManager;
import com.biopilot.common.mcp.McpServerConfig;
import com.biopilot.common.mcp.McpToolResult;
import com.biopilot.literature.domain.PaperCandidate;
import com.biopilot.literature.domain.SearchQuery;
import com.biopilot.literature.service.LiteratureMcpConfigService;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * MCP 文献检索源：把管理员配置的 paper-search-mcp 接进统一检索聚合。
 *
 * <p>paper-search-mcp 的 {@code search_papers} 返回结构化 papers 列表（不是散文），
 * 因此这里只做字段映射与年份过滤，不做文本解析。多个 server 的结果合并后交给聚合层
 * 统一去重；单个 server 失败只记入本次错误，不影响其他 server。</p>
 */
@Component
public class McpPaperProvider implements LiteratureProvider {

    private static final Logger log = LoggerFactory.getLogger(McpPaperProvider.class);
    private static final String TOOL = "search_papers";

    private final McpClientManager manager;
    private final LiteratureMcpConfigService configs;
    private final ObjectMapper json;

    public McpPaperProvider(McpClientManager manager,
                            LiteratureMcpConfigService configs,
                            ObjectMapper json) {
        this.manager = manager;
        this.configs = configs;
        this.json = json;
    }

    @Override
    public String name() {
        return "mcp";
    }

    @Override
    public List<PaperCandidate> search(SearchQuery query) {
        List<McpServerConfig> servers = configs.paperSearchConfigs();
        if (servers.isEmpty()) {
            return List.of();
        }
        List<PaperCandidate> out = new ArrayList<>();
        List<String> errors = new ArrayList<>();
        for (McpServerConfig server : servers) {
            if (!manager.tools(server.name()).contains(TOOL)) {
                errors.add(server.name() + ": 未发现 " + TOOL + " 工具");
                continue;
            }
            try {
                out.addAll(searchOne(server, query));
            } catch (Exception e) {
                errors.add(server.name() + ": " + e.getMessage());
                log.warn("MCP 文献检索失败（{}）: {}", server.name(), e.getMessage());
            }
        }
        if (out.isEmpty() && !errors.isEmpty()) {
            throw new IllegalStateException(String.join("; ", errors));
        }
        return out;
    }

    private List<PaperCandidate> searchOne(McpServerConfig server, SearchQuery query) {
        Map<String, Object> args = new LinkedHashMap<>();
        args.put("query", query.query());
        args.put("max_results_per_source", Math.max(3, query.limit()));
        args.put("sources", "all");
        // paper-search-mcp 的 year 只作用于 Semantic Scholar；年份区间在本地过滤
        if (query.yearFrom() != null && query.yearFrom().equals(query.yearTo())) {
            args.put("year", String.valueOf(query.yearFrom()));
        }
        McpToolResult result = manager.callTool(server.name(), TOOL, args);
        if (result.error()) {
            throw new IllegalStateException(brief(result.text()));
        }
        Map<String, Object> root = asMap(result);
        List<Map<String, Object>> papers = asPaperList(root);
        List<PaperCandidate> out = new ArrayList<>();
        for (Map<String, Object> paper : papers) {
            PaperCandidate candidate = toCandidate(paper);
            if (inYearRange(candidate.pubdate(), query.yearFrom(), query.yearTo())) {
                out.add(candidate);
            }
        }
        if (out.isEmpty()) {
            Object errors = root.get("errors");
            if (errors instanceof Map<?, ?> map && !map.isEmpty()) {
                throw new IllegalStateException(String.valueOf(map));
            }
        }
        return out;
    }

    private Map<String, Object> asMap(McpToolResult result) {
        Object structured = result.structured();
        if (structured instanceof String text) {
            try {
                return json.readValue(text, new TypeReference<Map<String, Object>>() {
                });
            } catch (Exception e) {
                throw new IllegalStateException("MCP 结构化结果是字符串但不可解析：" + brief(text));
            }
        }
        if (structured != null) {
            return json.convertValue(structured, new TypeReference<Map<String, Object>>() {
            });
        }
        String text = result.text();
        if (text == null || text.isBlank()) {
            throw new IllegalStateException("MCP 检索返回空结果");
        }
        try {
            return json.readValue(text, new TypeReference<Map<String, Object>>() {
            });
        } catch (Exception e) {
            throw new IllegalStateException("MCP 检索结果不是 JSON：" + brief(text));
        }
    }

    private List<Map<String, Object>> asPaperList(Map<String, Object> root) {
        Object papers = root.get("papers");
        if (!(papers instanceof List<?> list)) {
            return List.of();
        }
        List<Map<String, Object>> out = new ArrayList<>();
        for (Object item : list) {
            if (item instanceof Map<?, ?> map) {
                Map<String, Object> row = new LinkedHashMap<>();
                map.forEach((key, value) -> row.put(String.valueOf(key), value));
                out.add(row);
            }
        }
        return out;
    }

    private static PaperCandidate toCandidate(Map<String, Object> paper) {
        String id = text(paper.get("paper_id"));
        String doi = text(paper.get("doi"));
        String source = text(paper.get("source"));
        String published = text(paper.get("published_date"));
        String pdfUrl = text(paper.get("pdf_url"));
        String pmid = "pubmed".equalsIgnoreCase(source) ? id : "";
        return new PaperCandidate(
                id,
                text(paper.get("title")),
                text(paper.get("authors")),
                yearOf(published),
                "",
                doi,
                pmid,
                "",
                text(paper.get("abstract")),
                !pdfUrl.isBlank(),
                pdfUrl,
                text(paper.get("url")),
                source,
                integer(paper.get("citations")));
    }

    private static boolean inYearRange(String year, Integer from, Integer to) {
        if (from == null && to == null) {
            return true;
        }
        Integer value = integerOrNull(year);
        if (value == null) {
            return true; // 年份缺失不误杀；交由上层展示
        }
        return (from == null || value >= from) && (to == null || value <= to);
    }

    private static String yearOf(String published) {
        if (published == null) {
            return "";
        }
        String trimmed = published.trim();
        return trimmed.length() >= 4 ? trimmed.substring(0, 4) : trimmed;
    }

    private static String text(Object value) {
        return value == null ? "" : String.valueOf(value);
    }

    private static int integer(Object value) {
        Integer parsed = integerOrNull(value);
        return parsed == null ? 0 : parsed;
    }

    private static Integer integerOrNull(Object value) {
        if (value instanceof Number number) {
            return number.intValue();
        }
        try {
            return value == null ? null : Integer.valueOf(String.valueOf(value));
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private static String brief(String text) {
        String compact = text == null ? "" : text.replaceAll("\\s+", " ").trim();
        return compact.length() <= 300 ? compact : compact.substring(0, 300) + "…";
    }
}
