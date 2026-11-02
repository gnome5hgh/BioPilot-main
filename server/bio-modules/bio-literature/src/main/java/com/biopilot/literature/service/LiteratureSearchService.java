package com.biopilot.literature.service;

import com.biopilot.literature.domain.LiteratureSearchResult;
import com.biopilot.literature.domain.SearchQuery;
import java.util.Map;

/** 文献检索聚合：按请求选择检索源、汇总结果、去重并截断。 */
public interface LiteratureSearchService {

    /**
     * 前端入口：默认 10 条，返回前端既有契约的 map。
     *
     * Args:
     *     query: 检索词。
     *
     * Returns:
     *     {@code {results, sources, error?}}；全部源失败时带 error 文案。
     */
    Map<String, Object> search(String query);

    /**
     * 聚合检索：按 sources 过滤源，逐源执行并把异常记入 errors。
     *
     * Args:
     *     query: 检索参数。
     *
     * Returns:
     *     去重、截断后的结果与逐源统计。
     */
    LiteratureSearchResult searchForAgent(SearchQuery query);
}
