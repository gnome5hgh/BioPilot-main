package com.biopilot.literature.domain;

import java.util.List;
import java.util.Map;

/**
 * 聚合检索结果：条目、各源命中数与失败原因。
 *
 * @param results 去重并截断后的候选条目
 * @param sources 源名 → 该源返回条数
 * @param errors  源名 → 失败原因（成功的源不出现）
 */
public record LiteratureSearchResult(
        List<PaperCandidate> results,
        Map<String, Integer> sources,
        Map<String, String> errors) {
}
