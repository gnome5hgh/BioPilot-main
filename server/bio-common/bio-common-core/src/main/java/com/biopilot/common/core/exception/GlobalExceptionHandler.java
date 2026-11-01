package com.biopilot.common.core.exception;

import com.biopilot.common.core.R;
import org.springframework.http.HttpStatus;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.resource.NoResourceFoundException;

/** 全局异常兜底：业务异常转 R.fail，未知异常转通用失败文案（不泄内部细节）。 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(ServiceException.class)
    public R<Void> handleService(ServiceException e) {
        return R.fail(e.getMessage());
    }

    /** 路径不存在 / 方法不支持要如实回 404/405：吞进通用 500 会让前端调错路径时无从排查。 */
    @ExceptionHandler(NoResourceFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public R<Void> handleNotFound(NoResourceFoundException e) {
        return R.fail("接口不存在: " + e.getResourcePath());
    }

    @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
    @ResponseStatus(HttpStatus.METHOD_NOT_ALLOWED)
    public R<Void> handleMethodNotSupported(HttpRequestMethodNotSupportedException e) {
        return R.fail("请求方法不支持: " + e.getMessage());
    }

    @ExceptionHandler(Exception.class)
    public R<Void> handleUnknown(Exception e) {
        return R.fail("系统繁忙，请稍后重试");
    }
}
