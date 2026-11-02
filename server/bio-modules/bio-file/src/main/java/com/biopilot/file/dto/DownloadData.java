package com.biopilot.file.dto;

/** 文件/论文下载的字节、展示文件名与 MIME 类型。 */
public record DownloadData(byte[] data, String name, String contentType) {
}
