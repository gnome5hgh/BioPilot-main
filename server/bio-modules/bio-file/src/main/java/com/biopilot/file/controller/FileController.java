package com.biopilot.file.controller;

import cn.dev33.satoken.stp.StpUtil;
import com.biopilot.file.dto.DownloadData;
import com.biopilot.file.service.UploadedFileService;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/** 数据文件（对话附件）：路径与字段保持既有契约。 */
@RestController
@RequestMapping("/api/v1/files")
public class FileController {

    private final UploadedFileService service;

    public FileController(UploadedFileService service) {
        this.service = service;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Map<String, Object> upload(@RequestParam("file") MultipartFile file) {
        var view = service.upload(uid(), file);
        return Map.of("file_id", view.fileId(), "name", view.name(),
                "size", view.size(), "content_type", view.contentType(),
                "oss_key", view.ossKey() == null ? "" : view.ossKey());
    }

    @GetMapping
    public Map<String, Object> list() {
        return Map.of("files", service.list(uid()));
    }

    @GetMapping("/{fileId}/content")
    public ResponseEntity<byte[]> file(@PathVariable String fileId,
                                       @RequestParam(defaultValue = "false") boolean download) {
        DownloadData data = service.download(uid(), fileId);
        return DownloadResponses.of(data, download);
    }

    @DeleteMapping("/{fileId}")
    public Map<String, Object> delete(@PathVariable String fileId) {
        service.delete(uid(), fileId);
        return Map.of("status", "ok");
    }

    private long uid() {
        return StpUtil.getLoginIdAsLong();
    }
}
