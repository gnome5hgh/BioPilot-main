package com.biopilot.common.core.exception;

/** 业务异常：message 直接面向用户，GlobalExceptionHandler 统一转 R.fail。 */
public class ServiceException extends RuntimeException {

    private final int status;

    /** 默认 HTTP 200 + R.fail（沿用既有业务失败口径）。 */
    public ServiceException(String message) {
        this(200, message);
    }

    /** 指定 HTTP 状态码；新平台接口用它让 409/413/422 能被前端 axios 捕获。 */
    public ServiceException(int status, String message) {
        super(message);
        this.status = status;
    }

    public int getStatus() {
        return status;
    }
}
