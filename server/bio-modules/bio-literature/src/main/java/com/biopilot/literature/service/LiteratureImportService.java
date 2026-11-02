package com.biopilot.literature.service;

import java.util.Map;

/** 文献导入：检索结果 → 开放获取 PDF → 论文库（bio_paper + OSS）。 */
public interface LiteratureImportService {

    /**
     * 把一条检索结果导入论文库。
     *
     * Args:
     *     userId: 归属用户。
     *     body: 文献元数据（title/doi/pdf_url/authors/journal/pubdate）。
     *
     * Returns:
     *     {@code {status, paper_id, file_name}}。
     */
    Map<String, Object> importPaper(long userId, Map<String, Object> body);
}
