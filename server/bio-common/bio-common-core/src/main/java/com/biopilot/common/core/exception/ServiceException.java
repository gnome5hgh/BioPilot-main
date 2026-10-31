package com.biopilot.common.core.exception;

/** 业务异常：message 直接面向用户，GlobalExceptionHandler 统一转 R.fail。 */
public class ServiceException extends RuntimeException {

    public ServiceException(String message) {
        super(message);
    }
}
