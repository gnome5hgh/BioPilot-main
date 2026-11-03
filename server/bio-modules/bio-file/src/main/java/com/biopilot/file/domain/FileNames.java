package com.biopilot.file.domain;

import com.biopilot.common.core.exception.ServiceException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.text.Normalizer;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.HexFormat;
import java.util.Locale;

/** 文件展示名、归一化名与内容摘要的纯函数。 */
public final class FileNames {

    /** 与 {@code bio_file.name_key} 列宽一致。 */
    public static final int NAME_KEY_MAX = 255;

    private FileNames() {
    }

    /**
     * 清洗展示名：去掉路径分隔符与控制字符，超长截断；空值回退到默认名。
     *
     * @param raw      原始名字
     * @param maxLen   列宽上限
     * @param fallback 空值时使用的名字
     * @return 可落库的展示名
     */
    public static String displayName(String raw, int maxLen, String fallback) {
        String name = raw == null ? "" : raw.trim();
        if (name.isEmpty()) {
            return fallback;
        }
        if (name.length() > maxLen) {
            name = name.substring(0, maxLen);
        }
        String safe = name.replaceAll("[\\\\/:*?\"<>|\\x00-\\x1f]", "_").trim();
        return safe.isEmpty() ? fallback : safe;
    }

    /**
     * 归一化名：NFC + trim + lower，唯一键依据。
     *
     * @param name 展示名
     * @return 归一化名
     */
    public static String nameKey(String name) {
        String text = name == null ? "" : name.trim();
        if (text.isEmpty()) {
            throw new ServiceException(422, "文件名不能为空");
        }
        String key = Normalizer.normalize(text, Normalizer.Form.NFC)
                .toLowerCase(Locale.ROOT);
        if (key.length() > NAME_KEY_MAX) {
            throw new ServiceException(422, "文件名归一化后超过长度上限（"
                    + NAME_KEY_MAX + " 字符）");
        }
        return key;
    }

    /** 计算内容 sha256（文档版本键用）。 */
    public static String sha256(byte[] data) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(digest.digest(data));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("JVM 不支持 SHA-256", e);
        }
    }

    /** 计算字符串内容的 sha256。 */
    public static String sha256(String text) {
        return sha256(text == null ? new byte[0] : text.getBytes(StandardCharsets.UTF_8));
    }

    /** 当前 UTC 时间（与既有 created_at/updated_at 列格式一致）。 */
    public static String now() {
        return OffsetDateTime.now(ZoneOffset.UTC).toString();
    }
}
