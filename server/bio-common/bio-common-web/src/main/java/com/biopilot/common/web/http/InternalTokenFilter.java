package com.biopilot.common.web.http;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * 内部端点守卫：只拦 {@code /internal/*}，校验共享 token 与用户归属头。
 *
 * <p>这些端点从 Sa-Token 登录过滤中排除（调用方是 Python 引擎，没有浏览器会话），
 * 所以必须在这里单独把关，否则等于把内部能力暴露给任何能访问 8080 的调用方。
 * token 未配置时不校验 token（与 Python 侧内部端点同一语义），但
 * {@code X-User-Id} 始终必填——它是后续归属与审计的唯一依据。</p>
 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class InternalTokenFilter extends OncePerRequestFilter {

    @Value("${biopilot.internal-token:}")
    private String internalToken;

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getRequestURI().startsWith("/internal/");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        if (internalToken != null && !internalToken.isBlank()) {
            String provided = request.getHeader("X-Internal-Token");
            if (!internalToken.equals(provided)) {
                reject(response, "内部调用 token 无效");
                return;
            }
        }
        String userId = request.getHeader("X-User-Id");
        if (userId == null || userId.isBlank()) {
            reject(response, "缺少 X-User-Id 请求头");
            return;
        }
        chain.doFilter(request, response);
    }

    private static void reject(HttpServletResponse response, String message) throws IOException {
        response.setStatus(HttpServletResponse.SC_FORBIDDEN);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write("{\"code\":403,\"msg\":\"" + message + "\",\"data\":null}");
    }
}
