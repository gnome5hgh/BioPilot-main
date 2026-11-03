package com.biopilot.file.domain;

/** 平台文件在 OSS 里的对象键布局（与 Python 侧共用同一约定）。 */
public final class FileObjectKeys {

    private FileObjectKeys() {
    }

    /** 论文原文：users/&lt;uid&gt;/papers/&lt;paperId&gt;/&lt;name&gt;。 */
    public static String paper(String userId, String paperId, String name) {
        return "users/" + userId + "/papers/" + paperId + "/" + name;
    }

    /** 用户上传的数据文件：users/&lt;uid&gt;/files/uploads/&lt;fileId&gt;/&lt;name&gt;。 */
    public static String upload(String userId, String fileId, String name) {
        return "users/" + userId + "/files/uploads/" + fileId + "/" + name;
    }

    /** agent 分析产物：users/&lt;uid&gt;/files/analysis/&lt;runId&gt;/&lt;name&gt;。 */
    public static String artifact(String userId, String runId, String name) {
        return "users/" + userId + "/files/analysis/" + runId + "/" + name;
    }

    /**
     * 文档正文：users/&lt;uid&gt;/files/documents/&lt;docId&gt;.md。
     *
     * <p>键按 id 固定而不是按名字：改名不搬对象，同名新建也不会写进同一个键。</p>
     */
    public static String document(String userId, String docId) {
        return "users/" + userId + "/files/documents/" + docId + ".md";
    }
}
