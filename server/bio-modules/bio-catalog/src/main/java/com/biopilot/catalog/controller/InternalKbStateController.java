package com.biopilot.catalog.controller;

import com.biopilot.catalog.service.KbStateService;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 索引状态内部入口：只给 Python 引擎调用，不接受浏览器登录态。
 *
 * <p>{@code /internal/**} 由 {@code InternalTokenFilter} 校验 token 与
 * {@code X-User-Id}。状态机的写者只有这里与 {@code PaperService}，引擎不再直接
 * 写 `bio_paper`。</p>
 */
@RestController
@RequestMapping("/internal/kb")
public class InternalKbStateController {

    private final KbStateService states;

    public InternalKbStateController(KbStateService states) {
        this.states = states;
    }

    /**
     * 收敛派生状态；持索引锁时把遗留的 `indexing` 重排。
     *
     * @param userId 归属用户。
     * @param body   {@code {requeue_indexing}}
     * @return {@code {reset, queued, requeued}}
     */
    @PostMapping("/normalize")
    public Map<String, Object> normalize(@RequestHeader("X-User-Id") String userId,
                                         @RequestBody(required = false) Map<String, Object> body) {
        boolean requeue = body != null
                && Boolean.parseBoolean(String.valueOf(body.get("requeue_indexing")));
        return states.normalize(userId, requeue);
    }

    /**
     * 批量置为索引中。
     *
     * @param userId 归属用户。
     * @param body   {@code {paper_ids}}
     * @return {@code {accepted:[...]}}
     */
    @PostMapping("/indexing")
    public Map<String, Object> indexing(@RequestHeader("X-User-Id") String userId,
                                        @RequestBody Map<String, Object> body) {
        List<String> ids = states.markIndexing(userId, stringList(body.get("paper_ids")));
        return Map.of("accepted", ids);
    }

    /**
     * 批量写入索引结果。
     *
     * @param userId 归属用户。
     * @param body   {@code {results:[{paper_id, ok, chunks, error}]}}
     * @return {@code {applied:{paper_id: bool}}}
     */
    @PostMapping("/result")
    public Map<String, Object> result(@RequestHeader("X-User-Id") String userId,
                                      @RequestBody Map<String, Object> body) {
        List<Map<String, Object>> results = new ArrayList<>();
        Object raw = body.get("results");
        if (raw instanceof List<?> list) {
            for (Object item : list) {
                if (item instanceof Map<?, ?> map) {
                    @SuppressWarnings("unchecked")
                    Map<String, Object> row = (Map<String, Object>) map;
                    results.add(row);
                }
            }
        }
        return Map.of("applied", states.applyResults(userId, results));
    }

    private static List<String> stringList(Object raw) {
        List<String> ids = new ArrayList<>();
        if (raw instanceof List<?> list) {
            for (Object item : list) {
                if (item != null && !String.valueOf(item).isBlank()) {
                    ids.add(String.valueOf(item));
                }
            }
        }
        return ids;
    }
}
