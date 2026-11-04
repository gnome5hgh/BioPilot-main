package com.biopilot.file.dto;

/** 内部附件内容：字节 + 文件名 + MIME + OSS 键 + 摘要/版本/类型。 */
public record AgentFileData(byte[] data, String name, String contentType, String ossKey,
                            String sha256, long version, String kind) {
}
