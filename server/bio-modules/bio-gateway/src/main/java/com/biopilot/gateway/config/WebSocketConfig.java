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
                .setAllowedOriginPatterns("*")
                .addInterceptors(new HandshakeInterceptor() {
                    @Override
                    public boolean beforeHandshake(ServerHttpRequest request,
                                                   ServerHttpResponse response,
                                                   WebSocketHandler wsHandler,
                                                   Map<String, Object> attributes) {
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
}
