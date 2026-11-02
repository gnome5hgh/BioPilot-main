package com.biopilot.citation.controller;

import cn.dev33.satoken.stp.StpUtil;
import com.biopilot.citation.dto.CitationView;
import com.biopilot.citation.service.CitationService;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 引用库端点：列表/搜索、格式化、新增/编辑/删除、导出 .bib、从论文加入。 */
@RestController
@RequestMapping("/api/v1/citations")
public class CitationController {

    private final CitationService service;

    public CitationController(CitationService service) {
        this.service = service;
    }

    @GetMapping
    public Map<String, Object> list(@RequestParam(defaultValue = "") String q) {
        return Map.of("entries", service.list(q));
    }

    @PostMapping("/format")
    public Map<String, Object> format(@RequestBody Map<String, Object> body) {
        List<String> keys = keys(body);
        String style = body.get("style") == null ? "author-year" : String.valueOf(body.get("style"));
        return Map.of("text", service.format(keys, style), "style", style);
    }

    @GetMapping("/export")
    public Map<String, Object> export() {
        return Map.of("text", service.export());
    }

    @PostMapping("/from-paper")
    public Map<String, Object> fromPaper(@RequestBody Map<String, Object> body) {
        String paperId = String.valueOf(body.getOrDefault("paper_id", "")).trim();
        CitationView view = service.fromPaper(uid(), paperId);
        return Map.of("status", "ok", "result", view);
    }

    /** 按论文移出引用库（论文是引用的来源实体，作为路径参数）。 */
    @DeleteMapping("/by-paper/{paperId}")
    public Map<String, Object> removeByPaper(@PathVariable String paperId) {
        return Map.of("status", "ok", "removed", service.removeByPaper(uid(), paperId));
    }

    @PostMapping
    public Map<String, Object> add(@RequestBody Map<String, Object> body) {
        return Map.of("status", "ok", "result", service.addExternal(uid(), body));
    }

    @PutMapping("/{key}")
    public Map<String, Object> update(@PathVariable String key,
                                      @RequestBody Map<String, Object> body) {
        return Map.of("status", "ok", "result", service.updateExternal(key, body));
    }

    @DeleteMapping("/{key}")
    public Map<String, Object> delete(@PathVariable String key) {
        return Map.of("status", "ok", "removed", service.remove(key));
    }

    @SuppressWarnings("unchecked")
    private List<String> keys(Map<String, Object> body) {
        Object raw = body == null ? null : body.get("keys");
        if (!(raw instanceof List<?> list)) {
            return List.of();
        }
        return ((List<Object>) list).stream()
                .filter(value -> value != null && !String.valueOf(value).isBlank())
                .map(String::valueOf)
                .toList();
    }

    private long uid() {
        return StpUtil.getLoginIdAsLong();
    }
}
