package com.biopilot.file.domain;

/** 用户文件登记表的类型取值。 */
public enum UserFileKind {

    PAPER("paper", "论文"),
    DATA("data", "数据文件"),
    DOCUMENT("document", "文档"),
    ARTIFACT("artifact", "分析产物");

    private final String code;
    private final String label;

    UserFileKind(String code, String label) {
        this.code = code;
        this.label = label;
    }

    /** 落库的 kind 值。 */
    public String code() {
        return code;
    }

    /** 面向用户的类型名（冲突文案用）。 */
    public String label() {
        return label;
    }

    /**
     * 把库里的 kind 转成用户可读类型名；未知值按「文件」兜底。
     *
     * @param code 库里的 kind 值
     * @return 中文类型名
     */
    public static String labelOf(String code) {
        for (UserFileKind kind : values()) {
            if (kind.code.equals(code)) {
                return kind.label;
            }
        }
        return "文件";
    }
}
