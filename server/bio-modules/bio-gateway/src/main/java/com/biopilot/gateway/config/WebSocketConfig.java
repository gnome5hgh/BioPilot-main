package com.biopilot.gateway.config;

import cn.dev33.satoken.stp.StpUtil;
import com.biopilot.gateway.ws.TerminalRelayHandler;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.http.server.ServletServerHttpRequest;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;
import org.springframework.web.socket.server.HandshakeInterceptor;

import java.net.URI;
import java.util.Map;

/** WebSocket 装配：终端中继端点。

    登录态校验必须放在握手拦截器——握手是普通 HTTP 请求（cookie 里的 satoken
    可读）；afterConnectionEstablished 阶段请求上下文已销毁，StpUtil 拿不到。
    校验通过后把 userId 放进 attributes，供处理器注入信任头。
*/
@Configuration
@EnableWebSocket
public class WebSocketConfig implements WebSocketConfigurer {

    private final TerminalRelayHandler terminalRelayHandler;

    public WebSocketConfig(TerminalRelayHandler terminalRelayHandler) {
        this.terminalRelayHandler = terminalRelayHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(terminalRelayHandler, "/api/ws/terminal")
                .addInterceptors(new HandshakeInterceptor() {
                    @Override
                    public boolean beforeHandshake(ServerHttpRequest request,
                                                   ServerHttpResponse response,
                                                   WebSocketHandler wsHandler,
                                                   Map<String, Object> attributes) {
                        // 只接受同源握手：终端背后是宿主 shell，放开 * 会让任意
                        // 网页借用浏览器里的 satoken cookie 接管终端。
                        if (!sameOrigin(request)) {
                            response.setStatusCode(HttpStatus.FORBIDDEN);
                            return false;
                        }
                        try {
                            attributes.put("userId", StpUtil.getLoginIdAsString());
                            return true;
                        } catch (Exception e) {
                            response.setStatusCode(HttpStatus.UNAUTHORIZED);
                            return false;
                        }
                    }

                    @Override
                    public void afterHandshake(ServerHttpRequest request,
                                               ServerHttpResponse response,
                                               WebSocketHandler wsHandler,
                                               Exception exception) {
                        // 无需后处理
                    }
                });
    }

    /**
     * 同源判定：比较 Origin 与请求 Host 的主机名。
     *
     * <p>不比较端口：反向代理（nginx → 8080）会把请求端口改写成内部端口，
     * 而浏览器 Origin 是外部端口，按端口比较会在生产部署下误拒。没有 Origin
     * 头的非浏览器客户端（脚本/测试）放行，登录态校验仍然生效。</p>
     */
    private static boolean sameOrigin(ServerHttpRequest request) {
        String origin = request.getHeaders().getOrigin();
        if (origin == null || origin.isBlank()) {
            return true;
        }
        String host = request.getURI().getHost();
        if (host == null || host.isBlank()) {
            return false;
        }
        try {
            String originHost = URI.create(origin).getHost();
            return host.equalsIgnoreCase(originHost);
        } catch (Exception e) {
            return false;
        }
    }
}
