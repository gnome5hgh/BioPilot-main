package com.biopilot.common.web.http;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;

/** multipart/form-data 重组：把 Spring 已解析的文件/字段重新拼成上游可读的字节流。

    代理上传端点共用：Spring 的 MultipartFile 不能直接交给 Python 适配层，必须
    按 multipart 协议重新编码；文件名要防头注入（去引号/换行）。
*/
public final class MultipartRelay {

    private MultipartRelay() {
    }

    /** 重组结果：body 与 Content-Type（含 boundary）。 */
    public record Multipart(byte[] body, String contentType) {
    }

    /**
     * 按 multipart/form-data 组装一个文件与若干普通字段。
     *
     * @param fileName    原始文件名（helper 内部会清洗引号与换行）
     * @param contentType 文件 MIME 类型
     * @param fileBytes   文件字节
     * @param fields      普通表单字段（按 insertion order 写出）
     * @return 重组后的 body 与 Content-Type
     */
    public static Multipart build(String fileName, String contentType, byte[] fileBytes,
                                  Map<String, String> fields) {
        String boundary = "----biopilot" + UUID.randomUUID();
        String safeName = (fileName == null ? "file.bin" : fileName)
                .replace("\"", "").replace("\r", "").replace("\n", "");
        String type = contentType == null ? "application/octet-stream" : contentType;
        try {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            if (fields != null) {
                for (Map.Entry<String, String> entry : fields.entrySet()) {
                    out.write(("--" + boundary + "\r\n"
                            + "Content-Disposition: form-data; name=\"" + entry.getKey() + "\"\r\n\r\n"
                            + entry.getValue() + "\r\n").getBytes(StandardCharsets.UTF_8));
                }
            }
            out.write(("--" + boundary + "\r\n"
                    + "Content-Disposition: form-data; name=\"file\"; filename=\""
                    + safeName + "\"\r\n"
                    + "Content-Type: " + type + "\r\n\r\n").getBytes(StandardCharsets.UTF_8));
            out.write(fileBytes);
            out.write(("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.UTF_8));
            return new Multipart(out.toByteArray(),
                    "multipart/form-data; boundary=" + boundary);
        } catch (java.io.IOException e) {
            throw new IllegalStateException("multipart 重组失败", e);
        }
    }
}
