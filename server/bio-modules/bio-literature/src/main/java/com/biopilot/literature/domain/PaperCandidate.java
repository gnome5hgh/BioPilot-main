package com.biopilot.literature.domain;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * 文献候选：检索源返回的统一条目。
 *
 * <p>前端文献页与 agent 检索工具共用这一份结构；字段名沿用前端既有 snake_case 契约，
 * 新增字段只追加不重命名。{@code abstract} 是 Java 关键字，故属性名用
 * {@code abstractText}，序列化时仍输出 {@code abstract}。</p>
 *
 * @param id           条目唯一标识（优先 PMID，其次 PMCID/DOI）
 * @param title        标题
 * @param authors      作者串（分号分隔，保持检索源原样）
 * @param pubdate      出版年份
 * @param journal      期刊/会议
 * @param doi          DOI
 * @param pmid         PMID
 * @param pmcid        PMCID
 * @param abstractText 摘要
 * @param openAccess   是否开放获取
 * @param pdfUrl       开放获取 PDF 直链（没有则为空串）
 * @param url          条目详情页
 * @param source       检索源名（europepmc/openalex/...）
 * @param citations    被引次数（检索源未给则 0）
 */
@JsonInclude(JsonInclude.Include.NON_NULL)
public record PaperCandidate(
        String id,
        String title,
        String authors,
        String pubdate,
        String journal,
        String doi,
        String pmid,
        String pmcid,
        @JsonProperty("abstract") String abstractText,
        @JsonProperty("is_open_access") boolean openAccess,
        @JsonProperty("pdf_url") String pdfUrl,
        String url,
        String source,
        int citations) {
}
