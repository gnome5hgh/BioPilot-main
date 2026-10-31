package com.biopilot.common.core;

/**
 * 统一返回体（照搬 cde-base 的 R 结构：code/message/data）。
 */
public class R<T> {

    public static final int OK = 200;
    public static final int FAIL = 500;

    private int code;
    private String msg;
    private T data;

    public R() {
    }

    public R(int code, String msg, T data) {
        this.code = code;
        this.msg = msg;
        this.data = data;
    }

    /** 成功返回（带数据）。 */
    public static <T> R<T> ok(T data) {
        return new R<>(OK, "操作成功", data);
    }

    /** 成功返回（无数据）。 */
    public static R<Void> ok() {
        return new R<>(OK, "操作成功", null);
    }

    /** 失败返回。 */
    public static <T> R<T> fail(String msg) {
        return new R<>(FAIL, msg, null);
    }

    public int getCode() {
        return code;
    }

    public void setCode(int code) {
        this.code = code;
    }

    public String getMsg() {
        return msg;
    }

    public void setMsg(String msg) {
        this.msg = msg;
    }

    public T getData() {
        return data;
    }

    public void setData(T data) {
        this.data = data;
    }
}
