package com.biopilot.file.controller;

import com.biopilot.file.dto.DownloadData;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;

/** 文件/论文下载响应：inline（预览）与 attachment（下载）共用。 */
final class DownloadResponses {

    private DownloadResponses() {
    }

    static ResponseEntity<byte[]> of(DownloadData data, boolean download) {
        String quoted = URLEncoder.encode(data.name(), StandardCharsets.UTF_8)
                .replace("+", "%20");
        String disposition = (download ? "attachment" : "inline")
                + "; filename=\"" + quoted + "\"; filename*=UTF-8''" + quoted;
        MediaType type;
        try {
            type = MediaType.parseMediaType(data.contentType());
        } catch (Exception e) {
            type = MediaType.APPLICATION_OCTET_STREAM;
        }
        return ResponseEntity.ok()
                .contentType(type)
                .header("Content-Disposition", disposition)
                .body(data.data());
    }
}
