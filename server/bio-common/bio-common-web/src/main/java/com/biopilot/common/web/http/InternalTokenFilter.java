package com.biopilot.common.web.http;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
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
 * {@code X-User-Id} 始终必填——它是后续归属与审计的唯一依据。</p>
 *
 * <p>token 未配置时**只放行回环来源**：本地开发（Python 与 Java 同机）照常可用，
 * 但服务绑定在 0.0.0.0 时不再对局域网敞开——否则任意同网段主机自填
 * {@code X-User-Id} 就能读走他人论文。生产/容器部署必须配置共享 token。</p>
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
            if (!constantTimeEquals(internalToken, provided)) {
                reject(response, "内部调用 token 无效");
                return;
            }
        } else if (!isLoopback(request.getRemoteAddr())) {
            // 未配置 token 时只信任本机调用；容器部署必须显式配置共享 token
            reject(response, "内部调用 token 未配置，且来源不是回环地址");
            return;
        }
        String userId = request.getHeader("X-User-Id");
        if (userId == null || userId.isBlank()) {
            reject(response, "缺少 X-User-Id 请求头");
            return;
        }
        chain.doFilter(request, response);
    }

    /** 常量时间比较，避免按字节提前返回泄漏 token 前缀。 */
    private static boolean constantTimeEquals(String expected, String provided) {
        if (provided == null) {
            return false;
        }
        return MessageDigest.isEqual(
                expected.getBytes(StandardCharsets.UTF_8),
                provided.getBytes(StandardCharsets.UTF_8));
    }

    /** 判断来源地址是否回环（IPv4/IPv6 都覆盖）。 */
    private static boolean isLoopback(String remoteAddr) {
        if (remoteAddr == null || remoteAddr.isBlank()) {
            return false;
        }
        try {
            return InetAddress.getByName(remoteAddr).isLoopbackAddress();
        } catch (Exception e) {
            return false;
        }
    }

    private static void reject(HttpServletResponse response, String message) throws IOException {
        response.setStatus(HttpServletResponse.SC_FORBIDDEN);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write("{\"code\":403,\"msg\":\"" + message + "\",\"data\":null}");
    }
}
