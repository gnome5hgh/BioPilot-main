package com.biopilot.catalog.controller;

import cn.dev33.satoken.stp.StpUtil;
import com.biopilot.catalog.dto.DownloadData;
import com.biopilot.catalog.dto.PaperView;
import com.biopilot.catalog.service.PaperService;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/** 论文目录：路径与字段保持 Python 适配层既有契约。 */
@RestController
@RequestMapping("/agent/papers")
public class PaperController {

    private final PaperService service;

    public PaperController(PaperService service) {
        this.service = service;
    }

    @GetMapping
    public Map<String, Object> list() {
        return Map.of("papers", service.list(uid()));
    }

    @PostMapping(value = "/upload", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Map<String, Object> upload(@RequestParam("file") MultipartFile file,
                                      @RequestParam(value = "add_to_kb", defaultValue = "false")
                                      boolean addToKb) {
        PaperView paper = service.create(uid(), file, addToKb);
        return Map.of("status", "ok", "id", paper.id(),
                "oss_key", paper.ossKey(), "file_name", paper.fileName());
    }

    @PostMapping("/{paperId}")
    public Map<String, Object> register(@PathVariable String paperId,
                                        @RequestBody Map<String, Object> body) {
        service.register(uid(), paperId, body);
        return Map.of("status", "ok");
    }

    @GetMapping("/{paperId}/file")
    public ResponseEntity<byte[]> file(@PathVariable String paperId,
                                       @RequestParam(defaultValue = "false") boolean download) {
        DownloadData data = service.download(uid(), paperId);
        return DownloadResponses.of(data, download);
    }

    @PatchMapping("/{paperId}")
    public Map<String, Object> updateMetadata(@PathVariable String paperId,
                                              @RequestBody Map<String, Object> body) {
        service.updateMetadata(uid(), paperId, body);
        return Map.of("status", "ok");
    }

    @DeleteMapping("/{paperId}")
    public Map<String, Object> delete(@PathVariable String paperId) {
        String ossKey = service.delete(uid(), paperId);
        return Map.of("status", "ok", "oss_key", ossKey == null ? "" : ossKey);
    }

    private long uid() {
        return StpUtil.getLoginIdAsLong();
    }
}
