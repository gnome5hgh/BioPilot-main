package com.biopilot.catalog.controller;

import cn.dev33.satoken.stp.StpUtil;
import com.biopilot.catalog.dto.DocumentView;
import com.biopilot.catalog.service.DocumentService;
import java.util.Map;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 文档编辑器：路径与字段保持既有契约。 */
@RestController
@RequestMapping("/agent/documents")
public class DocumentController {

    private final DocumentService service;

    public DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping
    public Map<String, Object> list() {
        return Map.of("documents", service.list(uid()));
    }

    @PostMapping
    public Map<String, Object> create(@RequestBody Map<String, Object> body) {
        return service.create(uid(), body);
    }

    @GetMapping("/{docId}")
    public DocumentView get(@PathVariable String docId) {
        return service.get(uid(), docId);
    }

    @PutMapping("/{docId}")
    public Map<String, Object> save(@PathVariable String docId,
                                    @RequestBody Map<String, Object> body) {
        return service.save(uid(), docId, body);
    }

    @DeleteMapping("/{docId}")
    public Map<String, Object> delete(@PathVariable String docId) {
        service.delete(uid(), docId);
        return Map.of("status", "ok");
    }

    private long uid() {
        return StpUtil.getLoginIdAsLong();
    }
}
