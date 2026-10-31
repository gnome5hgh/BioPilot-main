package com.biopilot.admin.config;

import cn.dev33.satoken.exception.NotLoginException;
import cn.dev33.satoken.exception.NotPermissionException;
import cn.dev33.satoken.exception.NotRoleException;
import com.biopilot.common.core.R;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** Sa-Token 异常到 HTTP 码的映射：未登录 401、无角色/权限 403。

    独立放在 admin 模块：common-core 不依赖 Sa-Token（层次最低）。
*/
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
