package com.biopilot.catalog.controller;

import cn.dev33.satoken.stp.StpUtil;
import com.biopilot.catalog.service.PaperService;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 知识库论文清单与勾选：只写 kb_enabled，索引状态由 Python 内部接口维护。 */
@RestController
@RequestMapping("/agent/kb/papers")
public class KbPaperController {

    private final PaperService service;

    public KbPaperController(PaperService service) {
        this.service = service;
    }

    @GetMapping
    public Map<String, Object> list(@RequestParam(defaultValue = "all") String filter) {
        return Map.of("papers", service.kbList(uid(), filter));
    }

    @PostMapping("/add")
    public Map<String, Object> add(@RequestBody Map<String, Object> body) {
        List<String> ids = ids(body);
        return Map.of("status", "ok", "count", service.kbAdd(uid(), ids));
    }

    @PostMapping("/remove")
    public Map<String, Object> remove(@RequestBody Map<String, Object> body) {
        List<String> ids = ids(body);
        return Map.of("status", "ok", "count", service.kbRemove(uid(), ids));
    }

    @PostMapping("/retry")
    public Map<String, Object> retry(@RequestBody Map<String, Object> body) {
        List<String> ids = ids(body);
        return Map.of("status", "ok", "count", service.kbRetry(uid(), ids));
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
