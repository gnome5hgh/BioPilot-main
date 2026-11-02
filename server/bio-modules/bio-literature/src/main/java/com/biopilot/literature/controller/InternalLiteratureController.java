package com.biopilot.literature.controller;

import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.common.net.SafePdfFetcher;
import com.biopilot.literature.domain.LiteratureSearchResult;
import com.biopilot.literature.domain.SearchQuery;
import com.biopilot.literature.service.LiteratureSearchService;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 引擎内部文献检索入口：只给 Python agent 运行时调用，不接受浏览器登录态。
 *
 * <p>{@code /internal/**} 已从 Sa-Token 登录过滤中排除，由
 * {@code InternalTokenFilter} 单独校验内部 token 与 {@code X-User-Id}；筛选与聚合逻辑
 * 与前端入口共用 {@link LiteratureSearchService}。</p>
 */
@RestController
@RequestMapping("/internal/literature")
public class InternalLiteratureController {

    private final LiteratureSearchService searchService;

    public InternalLiteratureController(LiteratureSearchService searchService) {
        this.searchService = searchService;
    }

    /**
     * 执行聚合检索。
     *
     * @param userId 调用方用户（内部链路必带，用于归属与审计）
     * @param request 检索参数
     * @return {@code {results, sources, errors}}
     */
    @PostMapping("/search")
    public Map<String, Object> search(
            @RequestHeader(value = "X-User-Id", required = false) String userId,
            @RequestBody(required = false) SearchRequest request) {
        if (userId == null || userId.isBlank()) {
            throw new ServiceException(403, "缺少 X-User-Id 请求头");
        }
        SearchRequest req = request == null ? new SearchRequest(null, null, null, null, null) : request;
        SearchQuery query = new SearchQuery(
                req.q(),
                req.sources(),
                req.yearFrom(),
                req.yearTo(),
                req.limit() == null ? 10 : req.limit());
        LiteratureSearchResult result = searchService.searchForAgent(query);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("results", result.results());
        out.put("sources", result.sources());
        out.put("errors", result.errors());
        return out;
    }

    /**
     * 下载 PDF 字节（复用 bio-common-net 的 SSRF 逐跳校验与 `%PDF` 校验）。
     *
     * <p>只返回字节，**不登记论文库、不写 OSS**——agent 下载的论文按既有约定
     * 只落引擎工作区，是否进论文库由用户在网页决定。</p>
     *
     * @param userId  归属用户。
     * @param request {@code {url}}
     * @return 原始 PDF 字节。
     */
    @PostMapping("/fetch-pdf")
    public ResponseEntity<byte[]> fetchPdf(
            @RequestHeader(value = "X-User-Id", required = false) String userId,
            @RequestBody(required = false) FetchPdfRequest request) {
        if (userId == null || userId.isBlank()) {
            throw new ServiceException(403, "缺少 X-User-Id 请求头");
        }
        if (request == null || request.url() == null || request.url().isBlank()) {
            throw new ServiceException(422, "url 不能为空");
        }
        try {
            byte[] data = SafePdfFetcher.fetch(request.url());
            return ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_PDF)
                    .body(data);
        } catch (IllegalArgumentException e) {
            throw new ServiceException(422, "下载失败：" + e.getMessage());
        } catch (RuntimeException e) {
            throw new ServiceException(502, "下载失败：" + e.getMessage());
        }
    }

    /** 内部检索请求体；年份沿用 snake_case，与 Python 工具参数一致。 */
    public record SearchRequest(
            String q,
            List<String> sources,
            @JsonProperty("year_from") Integer yearFrom,
            @JsonProperty("year_to") Integer yearTo,
            Integer limit) {
    }

    /** PDF 下载请求体。 */
    public record FetchPdfRequest(String url) {
    }
}
