package com.biopilot.file.controller;

import com.biopilot.file.dto.DocumentSummary;
import com.biopilot.file.dto.DocumentView;
import com.biopilot.file.service.DocumentService;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * agent 文档内部入口：只给 Python 引擎调用，不接受浏览器登录态。
 *
 * <p>{@code /internal/**} 由 {@code InternalTokenFilter} 校验 token 与
 * {@code X-User-Id}；写入语义（同名覆盖、OSS 先落、版本条件更新）在
 * {@link DocumentService}。</p>
 */
@RestController
@RequestMapping("/internal/documents")
public class InternalDocumentController {

    private final DocumentService documents;

    public InternalDocumentController(DocumentService documents) {
        this.documents = documents;
    }

    @GetMapping
    public Map<String, Object> list(@RequestHeader("X-User-Id") String userId) {
        List<DocumentSummary> rows = documents.listForAgent(userId);
        return Map.of("documents", rows);
    }

    @GetMapping("/{id}")
    public DocumentView get(@RequestHeader("X-User-Id") String userId,
                            @PathVariable String id) {
        return documents.getForAgent(userId, id);
    }

    @GetMapping("/by-name")
    public DocumentView byName(@RequestHeader("X-User-Id") String userId,
                               @RequestParam("name") String name) {
        return documents.getByName(userId, name);
    }

    @PostMapping("/save")
    public Map<String, Object> save(@RequestHeader("X-User-Id") String userId,
                                    @RequestBody Map<String, Object> body) {
        String name = String.valueOf(body.getOrDefault("name", ""));
        String content = String.valueOf(body.getOrDefault("content", ""));
        Long expected = null;
        Object raw = body.get("expected_version");
        if (raw != null && !String.valueOf(raw).isBlank()) {
            try {
                expected = Long.parseLong(String.valueOf(raw));
            } catch (NumberFormatException e) {
                throw new com.biopilot.common.core.exception.ServiceException(
                        422, "expected_version 必须是整数");
            }
        }
        return documents.saveByName(userId, name, content, expected);
    }

    @DeleteMapping("/{id}")
    public Map<String, Object> delete(@RequestHeader("X-User-Id") String userId,
                                      @PathVariable String id) {
        documents.deleteForAgent(userId, id);
        return Map.of("status", "ok");
    }
}
