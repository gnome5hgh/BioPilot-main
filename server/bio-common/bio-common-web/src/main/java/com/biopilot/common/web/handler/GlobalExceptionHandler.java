package com.biopilot.common.web.handler;

import com.biopilot.common.core.R;
import com.biopilot.common.core.exception.ServiceException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

/** 全局异常兜底：业务异常转 R.fail，未知异常转通用失败文案（不泄内部细节）。

    排在最后：更具体的 advice（如 Sa-Token 的 401/403）必须先匹配。
*/
@Order(Ordered.LOWEST_PRECEDENCE)
@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(ServiceException.class)
    public ResponseEntity<R<Void>> handleService(ServiceException e) {
        return ResponseEntity.status(e.getStatus()).body(R.fail(e.getMessage()));
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

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    @ResponseStatus(HttpStatus.PAYLOAD_TOO_LARGE)
    public R<Void> handleUploadTooLarge(MaxUploadSizeExceededException e) {
        return R.fail("文件超过上传大小上限");
    }

    @ExceptionHandler(Exception.class)
    public R<Void> handleUnknown(Exception e) {
        // 未知异常必须留全栈：对外只回通用文案，对内没有这行日志就无法排障
        log.error("未处理异常", e);
        return R.fail("系统繁忙，请稍后重试");
    }
}
