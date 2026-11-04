package com.biopilot.file.domain;

/** 平台文件在 OSS 里的对象键布局（与 Python 侧共用同一约定）。 */
public final class FileObjectKeys {

    private FileObjectKeys() {
    }

    /**
     * 把用户/run/文件名等片段收敛成可安全拼进对象键的字面量。
     *
     * <p>对象键是 Java 写的，但 userId/runId/name 可能来自内部请求头或上传文件名；
     * 不收敛就可能出现 {@code users/../../victim/...} 这类越界键。只保留字母、数字、
     * 点、下划线和短横线，其他字符替换为下划线，并去掉 {@code ..}。</p>
     */
    public static String safeSegment(String value) {
        String text = value == null ? "" : value.trim();
        text = text.replaceAll("[^A-Za-z0-9._-]", "_");
        text = text.replace("..", "_");
        if (text.isBlank()) {
            return "unknown";
        }
        return text.length() > 128 ? text.substring(0, 128) : text;
    }

    /** 论文原文：users/&lt;uid&gt;/papers/&lt;paperId&gt;/&lt;name&gt;。 */
    public static String paper(String userId, String paperId, String name) {
        return "users/" + safeSegment(userId) + "/papers/" + safeSegment(paperId)
                + "/" + safeSegment(name);
    }

    /** 用户上传的数据文件：users/&lt;uid&gt;/files/uploads/&lt;fileId&gt;/&lt;name&gt;。 */
    public static String upload(String userId, String fileId, String name) {
        return "users/" + safeSegment(userId) + "/files/uploads/" + safeSegment(fileId)
                + "/" + safeSegment(name);
    }

    /** agent 分析产物：users/&lt;uid&gt;/files/analysis/&lt;runId&gt;/&lt;fileId&gt;/&lt;name&gt;。 */
    public static String artifact(String userId, String runId, String fileId, String name) {
        return "users/" + safeSegment(userId) + "/files/analysis/"
                + safeSegment(runId) + "/" + safeSegment(fileId) + "/" + safeSegment(name);
    }

    /**
     * 文档正文：users/&lt;uid&gt;/files/documents/&lt;docId&gt;/&lt;version&gt;-&lt;sha&gt;.md。
     *
     * <p>每次写入用新键，数据库条件更新成功后才切换指针；并发写者各自落自己的键，
     * 不会互相覆盖，也不会留下“指针已更新、对象还是旧内容”或反之的中间态。</p>
     */
    public static String document(String userId, String docId, long version, String sha256,
                                  String attempt) {
        // attempt 每次写入都不同：两个并发写者即使版本与内容相同，也各落一个键，
        // 失败方的补偿删除不会碰到成功方仍在引用的对象。
        return "users/" + safeSegment(userId) + "/files/documents/" + safeSegment(docId)
                + "/" + version + "-" + safeSegment(sha256) + "-"
                + safeSegment(attempt) + ".md";
    }
}
