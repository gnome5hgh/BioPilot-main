package com.biopilot.common.satoken.handler;

import cn.dev33.satoken.exception.NotLoginException;
import cn.dev33.satoken.exception.NotPermissionException;
import cn.dev33.satoken.exception.NotRoleException;
import com.biopilot.common.core.R;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** Sa-Token 异常到 HTTP 码的映射：未登录 401、无角色/权限 403。

    必须排在全局兜底之前：通用 Exception handler 会先吞掉 NotRoleException，
    导致 403 被错误映射成 200 + R.fail。
*/
@Order(Ordered.HIGHEST_PRECEDENCE)
@RestControllerAdvice
public class SaTokenExceptionAdvice {

    @ExceptionHandler(NotLoginException.class)
    @ResponseStatus(HttpStatus.UNAUTHORIZED)
    public R<Void> handleNotLogin(NotLoginException e) {
        return new R<>(401, "未登录或登录已失效", null);
    }

    @ExceptionHandler({NotRoleException.class, NotPermissionException.class})
    @ResponseStatus(HttpStatus.FORBIDDEN)
    public R<Void> handleNoPermission(Exception e) {
        return new R<>(403, "无权访问", null);
    }
}
