package com.biopilot.common.core.exception;

import com.biopilot.common.core.R;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** 全局异常兜底：业务异常转 R.fail，未知异常转通用失败文案（不泄内部细节）。 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(ServiceException.class)
    public R<Void> handleService(ServiceException e) {
        return R.fail(e.getMessage());
    }



    @ExceptionHandler(Exception.class)
    public R<Void> handleUnknown(Exception e) {
        return R.fail("系统繁忙，请稍后重试");
    }
}
