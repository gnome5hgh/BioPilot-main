package com.biopilot.literature.service;

import com.biopilot.literature.domain.LiteratureSearchResult;
import com.biopilot.literature.domain.PaperCandidate;
import com.biopilot.literature.domain.SearchQuery;
import com.biopilot.literature.service.provider.LiteratureProvider;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * 文献检索聚合：按请求选择检索源、汇总结果、去重并截断。
 *
 * <p>前端文献页与 agent 检索工具都走这里，区别只在入口：前端要求登录，agent 走
 * {@code /internal/literature/search} 内部端点。单个源失败不拖垮整体——失败原因记入
 * {@code errors}，其余源的结果照常返回。</p>
 */
@Service
public class LiteratureSearchService {

    private static final Logger log = LoggerFactory.getLogger(LiteratureSearchService.class);

    private final List<LiteratureProvider> providers;

    public LiteratureSearchService(List<LiteratureProvider> providers) {
        this.providers = providers;
    }

    /**
     * 前端入口：默认 10 条，返回前端既有契约的 map。
     *
     * @param query 检索词
     * @return {@code {results, sources, error?}}；全部源失败时带 error 文案
     */
    public Map<String, Object> search(String query) {
        if (query == null || query.isBlank()) {
            return Map.of("results", List.of());
        }
        LiteratureSearchResult result = searchForAgent(
                new SearchQuery(query, List.of(), null, null, 10));
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("results", result.results());
        out.put("sources", result.sources());
        if (result.results().isEmpty() && !result.errors().isEmpty()) {
            out.put("error", String.join("; ", result.errors().values()));
        }
        return out;
    }

    /**
     * 聚合检索：按 sources 过滤源，逐源执行并把异常记入 errors。
     *
     * @param query 检索参数
     * @return 去重、截断后的结果与逐源统计
     */
    public LiteratureSearchResult searchForAgent(SearchQuery query) {
        Map<String, Integer> counts = new LinkedHashMap<>();
        Map<String, String> errors = new LinkedHashMap<>();
        if (query.query() == null || query.query().isBlank()) {
            return new LiteratureSearchResult(List.of(), counts, errors);
        }
        List<LiteratureProvider> selected = selectProviders(query);
        if (selected.isEmpty()) {
            errors.put("sources", "没有可用的检索源：" + query.sources());
            return new LiteratureSearchResult(List.of(), counts, errors);
        }
        List<PaperCandidate> all = new ArrayList<>();
        for (LiteratureProvider provider : selected) {
            try {
                List<PaperCandidate> rows = provider.search(query);
                counts.put(provider.name(), rows.size());
                all.addAll(rows);
            } catch (Exception e) {
                counts.put(provider.name(), 0);
                errors.put(provider.name(), String.valueOf(e.getMessage()));
                log.warn("文献检索源 {} 失败: {}", provider.name(), e.getMessage());
            }
        }
        List<PaperCandidate> deduped = dedupe(all);
        if (deduped.size() > query.limit()) {
            deduped = List.copyOf(deduped.subList(0, query.limit()));
        }
        return new LiteratureSearchResult(deduped, counts, errors);
    }

    private List<LiteratureProvider> selectProviders(SearchQuery query) {
        if (query.sources().isEmpty()) {
            return providers;
        }
        Set<String> wanted = new LinkedHashSet<>(query.sources());
        return providers.stream().filter(p -> wanted.contains(p.name())).toList();
    }

    /** 去重键：DOI > PMID > 规范化标题。保留首次出现的条目。 */
    private static List<PaperCandidate> dedupe(List<PaperCandidate> rows) {
        Map<String, PaperCandidate> seen = new LinkedHashMap<>();
        for (PaperCandidate row : rows) {
            seen.putIfAbsent(dedupeKey(row), row);
        }
        return new ArrayList<>(seen.values());
    }

    private static String dedupeKey(PaperCandidate p) {
        if (notBlank(p.doi())) {
            return "doi:" + p.doi().toLowerCase(Locale.ROOT);
        }
        if (notBlank(p.pmid())) {
            return "pmid:" + p.pmid();
        }
        return "title:" + (p.title() == null ? "" : p.title().toLowerCase(Locale.ROOT)
                .replaceAll("[^a-z0-9]", ""));
    }

    private static boolean notBlank(String value) {
        return value != null && !value.isBlank();
    }
}
