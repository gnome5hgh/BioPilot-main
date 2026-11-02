package com.biopilot.file.dto;

/** 内部附件内容：字节 + 文件名 + MIME + OSS 键（引擎落本地副本用）。 */
public record AgentFileData(byte[] data, String name, String contentType, String ossKey) {
}
