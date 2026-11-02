package com.biopilot.kb.controller;

import cn.dev33.satoken.stp.StpUtil;
import com.biopilot.kb.service.KbPaperService;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.DeleteMapping;

/** 知识库论文清单与勾选：只写 kb 列，索引状态由 Python 经内部接口上报。 */
@RestController
@RequestMapping("/api/v1/kb/papers")
public class KbPaperController {

    private final KbPaperService service;

    public KbPaperController(KbPaperService service) {
        this.service = service;
    }

    @GetMapping
    public Map<String, Object> list(@RequestParam(defaultValue = "all") String filter) {
        return Map.of("papers", service.list(uid(), filter));
    }

    @PostMapping
    public Map<String, Object> add(@RequestBody Map<String, Object> body) {
        return Map.of("status", "ok", "count", service.add(uid(), ids(body)));
    }

    @DeleteMapping
    public Map<String, Object> remove(@RequestBody Map<String, Object> body) {
        return Map.of("status", "ok", "count", service.remove(uid(), ids(body)));
    }

    @PostMapping("/retry")
    public Map<String, Object> retry(@RequestBody Map<String, Object> body) {
        return Map.of("status", "ok", "count", service.retry(uid(), ids(body)));
    }

    @SuppressWarnings("unchecked")
    private List<String> ids(Map<String, Object> body) {
        Object raw = body == null ? null : body.get("ids");
        if (!(raw instanceof List<?> list)) {
            return List.of();
        }
        return ((List<Object>) list).stream()
                .filter(v -> v != null && !String.valueOf(v).isBlank())
                .map(String::valueOf)
                .toList();
    }

    private long uid() {
        return StpUtil.getLoginIdAsLong();
    }
}
