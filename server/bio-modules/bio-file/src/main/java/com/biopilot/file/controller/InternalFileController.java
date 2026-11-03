package com.biopilot.file.controller;

import com.biopilot.file.dto.AgentFileData;
import com.biopilot.file.dto.FileListItem;
import com.biopilot.file.dto.FileView;
import com.biopilot.file.service.UploadedFileService;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/** 数据文件/分析产物的内部入口：读字节、按 run 列举、删除、登记产物。 */
@RestController
@RequestMapping("/internal/files")
public class InternalFileController {

    private final UploadedFileService files;

    public InternalFileController(UploadedFileService files) {
        this.files = files;
    }

    @GetMapping
    public Map<String, Object> list(@RequestHeader("X-User-Id") String userId,
                                    @RequestParam(value = "run_id", required = false) String runId,
                                    @RequestParam(value = "limit", defaultValue = "100") int limit) {
        List<FileListItem> rows = runId == null || runId.isBlank()
                ? files.listForAgent(userId, Math.min(Math.max(limit, 1), 500))
                : files.listByRun(userId, runId, Math.min(Math.max(limit, 1), 500));
        return Map.of("files", rows);
    }

    @GetMapping("/{id}")
    public ResponseEntity<byte[]> content(@RequestHeader("X-User-Id") String userId,
                                          @PathVariable String id) {
        AgentFileData data = files.loadForAgent(userId, id);
        String encoded = URLEncoder.encode(data.name() == null ? "" : data.name(),
                StandardCharsets.UTF_8).replace("+", "%20");
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(data.contentType() == null
                        ? "application/octet-stream" : data.contentType()))
                .header("X-File-Name", encoded)
                .header("X-File-Size", String.valueOf(data.data().length))
                .header("X-Oss-Key", data.ossKey() == null ? "" : data.ossKey())
                .header("X-Content-Sha256", data.sha256() == null ? "" : data.sha256())
                .header("X-File-Version", String.valueOf(data.version()))
                .header("X-File-Kind", data.kind() == null ? "" : data.kind())
                .body(data.data());
    }

    @DeleteMapping("/{id}")
    public Map<String, Object> delete(@RequestHeader("X-User-Id") String userId,
                                      @PathVariable String id) {
        files.deleteForAgent(userId, id);
        return Map.of("status", "ok");
    }

    @PostMapping(value = "/artifacts", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public Map<String, Object> artifact(@RequestHeader("X-User-Id") String userId,
                                        @RequestParam("run_id") String runId,
                                        @RequestParam("file") MultipartFile file) {
        FileView view = files.uploadArtifact(userId, runId, file);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("file_id", view.fileId());
        out.put("name", view.name());
        out.put("size", view.size());
        out.put("content_type", view.contentType());
        out.put("oss_key", view.ossKey());
        out.put("version", view.version());
        return out;
    }
}
