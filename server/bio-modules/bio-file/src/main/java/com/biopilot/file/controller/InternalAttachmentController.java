package com.biopilot.file.controller;

import com.biopilot.file.dto.AgentFileData;
import com.biopilot.file.service.PaperService;
import com.biopilot.file.service.UploadedFileService;
import com.biopilot.common.core.exception.ServiceException;
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
 * 别人的文件是否存在。{@code /internal/**} 由 {@code InternalTokenFilter} 校验
 * token 与用户头。</p>
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

    /**
     * 取回附件字节。
     *
     * @param kind   {@code paper} 或 {@code file}。
     * @param id     对应业务 id。
     * @param userId 归属用户。
     * @return 原始字节；文件名/大小/OSS 键放在响应头，避免二次请求。
     */
    @GetMapping("/{kind}/{id}")
    public ResponseEntity<byte[]> content(@PathVariable String kind,
                                          @PathVariable String id,
                                          @RequestHeader("X-User-Id") String userId) {
        AgentFileData data = switch (kind) {
            case "paper" -> papers.loadForAgent(userId, id);
            case "file" -> files.loadForAgent(userId, id);
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
