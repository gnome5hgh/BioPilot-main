package com.biopilot.file.controller;

import com.biopilot.file.service.DocumentService;
import java.util.Map;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * agent 成稿入库的内部入口：只给 Python 引擎调用，不接受浏览器登录态。
 *
 * <p>{@code /internal/**} 由 {@code InternalTokenFilter} 校验 token 与
 * {@code X-User-Id}；写入语义（同名覆盖、OSS 先落）在 {@link DocumentService}。</p>
 */
@RestController
@RequestMapping("/internal/documents")
public class InternalDocumentController {

    private final DocumentService documents;

    public InternalDocumentController(DocumentService documents) {
        this.documents = documents;
    }

    /**
     * 按名字保存 markdown 文档。
     *
     * @param userId 归属用户（内部链路必带）
     * @param body   {@code {name, content}}
     * @return {@code {status, id, name, created}}
     */
    @PostMapping("/save")
    public Map<String, Object> save(@RequestHeader("X-User-Id") String userId,
                                    @RequestBody Map<String, Object> body) {
        String name = String.valueOf(body.getOrDefault("name", ""));
        String content = String.valueOf(body.getOrDefault("content", ""));
        return documents.saveByName(userId, name, content);
    }
}
