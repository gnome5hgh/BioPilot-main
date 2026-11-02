package com.biopilot.literature.domain;

import java.util.List;

/**
 * 文献检索请求：前端文献页与 agent 工具共用的参数结构。
 *
 * @param query    检索词
 * @param sources  指定检索源；空列表表示使用全部已启用源
 * @param yearFrom 起始年份（可选）
 * @param yearTo   截止年份（可选）
 * @param limit    返回条数（1-20，越界自动夹取）
 */
public record SearchQuery(
        String query,
        List<String> sources,
        Integer yearFrom,
        Integer yearTo,
        int limit) {

    public SearchQuery {
        sources = sources == null ? List.of() : List.copyOf(sources);
        if (limit <= 0) {
            limit = 10;
        }
        if (limit > 20) {
            limit = 20;
        }
    }
}
