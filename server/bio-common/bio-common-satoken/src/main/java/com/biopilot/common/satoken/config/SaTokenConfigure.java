package com.biopilot.common.satoken.config;

import cn.dev33.satoken.context.SaHolder;
import cn.dev33.satoken.filter.SaServletFilter;
import cn.dev33.satoken.interceptor.SaInterceptor;
import cn.dev33.satoken.stp.StpUtil;
import com.biopilot.common.core.R;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/** Sa-Token 全局过滤器：放行健康检查与登录/注册，其余接口要求登录。

    用 Servlet 过滤器而非拦截器：无映射 handler 的路由（404）也会先过鉴权，
    NotLoginException 由 error 回调统一转 401 JSON，不再走 error page 二次异常。
*/
@Configuration
public class SaTokenConfigure implements WebMvcConfigurer {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        // 注解解析器（@SaCheckRole 等）：路由登录检查在下面的过滤器里，这里只管注解
        registry.addInterceptor(new SaInterceptor());
    }

    @Bean
    public SaServletFilter saTokenFilter() {
        return new SaServletFilter()
                .addInclude("/**")
                // /internal/** 是引擎内部调用，没有浏览器登录态；由 InternalTokenFilter
                // 单独校验内部 token 与 X-User-Id，不能只靠这里的排除。
                .addExclude("/health", "/auth/login", "/auth/register", "/error", "/internal/**")
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
                        return objectMapper.writeValueAsString(new R<>(401, e.getMessage(), null));
                    } catch (Exception jsonError) {
                        return R.fail(e.getMessage()).getMsg();
                    }
                });
    }
}
