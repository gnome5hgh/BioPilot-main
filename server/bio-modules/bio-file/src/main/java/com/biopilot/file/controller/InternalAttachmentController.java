package com.biopilot.file.controller;

import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.file.dto.AgentFileData;
import com.biopilot.file.service.PaperService;
import com.biopilot.file.service.UploadedFileService;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 附件内容内部入口：只给 Python 引擎取回「本人」的论文/数据文件字节。
 *
 * <p>身份只认 {@code (kind, id, X-User-Id)}；不存在与无权共用 404，避免泄露
 * 别人的文件是否存在。{@code kind} 接受 {@code paper}、{@code file}/{@code data}、
 * {@code artifact}；文档正文走 {@code /internal/documents/{id}} 的 JSON 端点。</p>
 */
@RestController
@RequestMapping("/internal/attachments")
public class InternalAttachmentController {

    private final PaperService papers;
    private final UploadedFileService files;

    public InternalAttachmentController(PaperService papers, UploadedFileService files) {
        this.papers = papers;
        this.files = files;
    }

    @GetMapping("/{kind}/{id}")
    public ResponseEntity<byte[]> content(@PathVariable String kind,
                                          @PathVariable String id,
                                          @RequestHeader("X-User-Id") String userId) {
        AgentFileData data = switch (kind) {
            case "paper" -> papers.loadForAgent(userId, id);
            case "file", "data", "artifact" -> files.loadForAgent(userId, id);
            default -> throw new ServiceException(422, "未知附件类型: " + kind);
        };
        String encoded = URLEncoder.encode(
                data.name() == null ? "" : data.name(), StandardCharsets.UTF_8)
                .replace("+", "%20");
        return ResponseEntity.ok()
                .contentType(parseType(data.contentType()))
                .header("X-File-Name", encoded)
                .header("X-File-Size", String.valueOf(data.data().length))
                .header("X-Oss-Key", data.ossKey() == null ? "" : data.ossKey())
                .header("X-Content-Sha256", data.sha256() == null ? "" : data.sha256())
                .header("X-File-Version", String.valueOf(data.version()))
                .header("X-File-Kind", data.kind() == null ? "" : data.kind())
                .body(data.data());
    }

    private static MediaType parseType(String value) {
        try {
            return MediaType.parseMediaType(value);
        } catch (RuntimeException e) {
            return MediaType.APPLICATION_OCTET_STREAM;
        }
    }
}
