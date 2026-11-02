package com.biopilot.literature.service.provider;

import com.biopilot.literature.domain.PaperCandidate;
import com.biopilot.literature.domain.SearchQuery;
import java.util.List;

/**
 * 文献检索源接口：一个实现对应一个可配置的检索后端。
 *
 * <p>新增源（Europe PMC、MCP server、其他 HTTP API）只需实现本接口并注册为 Spring Bean，
 * 聚合服务会自动纳入。实现方负责把源自己的响应映射成 {@link PaperCandidate}；超时、
 * 非 2xx、解析失败都应抛异常，由聚合服务记入 {@code errors}，不得返回静默空列表。</p>
 */
public interface LiteratureProvider {

    /** 源名（与 {@link SearchQuery#sources()} 中的名字一致）。 */
    String name();

    /** 执行一次检索；失败抛异常。 */
    List<PaperCandidate> search(SearchQuery query) throws Exception;
}
