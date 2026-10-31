package com.biopilot.admin.config;

import cn.dev33.satoken.context.SaHolder;
import cn.dev33.satoken.filter.SaServletFilter;
import cn.dev33.satoken.stp.StpUtil;
import com.biopilot.common.core.R;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** Sa-Token 全局过滤器：放行健康检查与登录/注册，其余接口要求登录。

    用 Servlet 过滤器而非拦截器：无映射 handler 的路由（404）也会先过鉴权，
    NotLoginException 由 error 回调统一转 401 JSON，不再走 error page 二次异常。
*/
@Configuration
public class SaTokenConfigure {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Bean
    public SaServletFilter saTokenFilter() {
        return new SaServletFilter()
                .addInclude("/**")
                .addExclude("/health", "/auth/login", "/auth/register", "/error")
                .setAuth(obj -> StpUtil.checkLogin())
                .setError(e -> {
                    try {
                        SaHolder.getContext().getResponse()
                                .setStatus(401)
                                .setHeader("Content-Type", "application/json;charset=UTF-8");
                    } catch (Exception ignore) {
                        // 响应头不可写时仍回 body（由过滤器兜底输出）
                    }
                    try {
                        return objectMapper.writeValueAsString(R.fail(e.getMessage()));
                    } catch (Exception jsonError) {
                        return R.fail(e.getMessage()).getMsg();
                    }
                });
    }
}
