package com.biopilot.catalog.controller;

import com.biopilot.catalog.dto.FileView;
import com.biopilot.catalog.service.UploadedFileService;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/**
 * 分析产物内部入口：只给 Python 引擎登记沙箱产物。
 *
 * <p>与面向浏览器的 `/agent/files/upload` 不同，这里不做同名检查（跨 run 重名是
 * 正常现象），对象键用 run_id 分段隔离。</p>
 */
@RestController
@RequestMapping("/internal/files")
public class InternalFileController {

    private final UploadedFileService files;

    public InternalFileController(UploadedFileService files) {
        this.files = files;
    }

    /**
     * 登记一个分析产物。
     *
     * @param userId 归属用户。
     * @param runId  本次沙箱运行标识。
     * @param file   产物文件。
     * @return {@code {file_id, name, size, content_type, oss_key}}。
     */
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
        return out;
    }
}
