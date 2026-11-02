package com.biopilot.gateway.ws;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.time.Duration;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ConcurrentHashMap;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.ConcurrentWebSocketSessionDecorator;
import org.springframework.web.socket.handler.TextWebSocketHandler;

/** 终端 WebSocket 中继：浏览器 ⇄ SpringBoot ⇄ Python 适配层 PTY。

    登录态校验在握手后立即做（浏览器 WS 自动携带 satoken cookie）；归属经
    X-User-Id 头注入上游——信任边界与 HTTP 代理同一套。两侧帧都是文本帧。
    发送用 ConcurrentWebSocketSessionDecorator 串行化（Spring 会话不并发安全）。
*/
@Component
public class TerminalRelayHandler extends TextWebSocketHandler {

    private static final Logger log = LoggerFactory.getLogger(TerminalRelayHandler.class);
    /** 适配层终端端点：只允许回环/内网（与适配层监听约束同侧）。
        容器部署经 biopilot.adapter-base 派生（env 可覆盖）。 */
    @org.springframework.beans.factory.annotation.Value(
            "${biopilot.adapter-base:http://127.0.0.1:8300}")
    private String adapterBase;

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    private URI adapterWs() {
        return URI.create(adapterBase.replaceFirst("^http", "ws") + "/ws/terminal");
    }
    private final ConcurrentHashMap<WebSocketSession, WebSocket> upstreams =
            new ConcurrentHashMap<>();

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        WebSocketSession outbound = new ConcurrentWebSocketSessionDecorator(
                session, 5000, 1_000_000);
        // userId 由握手拦截器放入（见 WebSocketConfig）：那时 HTTP 上下文还在
        final String userId = String.valueOf(session.getAttributes().get("userId"));
        if (userId == null || "null".equals(userId)) {
            log.info("终端连接拒绝：握手未通过登录校验");
            close(session, CloseStatus.NOT_ACCEPTABLE.withReason("未登录"));
            return;
        }
        WebSocket.Listener listener = new WebSocket.Listener() {
            @Override
            public CompletionStage<?> onText(WebSocket ws, CharSequence data, boolean last) {
                try {
                    outbound.sendMessage(new TextMessage(data.toString()));
                } catch (Exception e) {
                    log.debug("终端下行写失败（客户端断开）: {}", e.getMessage());
                }
                return WebSocket.Listener.super.onText(ws, data, last);
            }

            @Override
            public CompletionStage<?> onClose(WebSocket ws, int statusCode, String reason) {
                close(session, CloseStatus.NORMAL);
                return WebSocket.Listener.super.onClose(ws, statusCode, reason);
            }

            @Override
            public void onError(WebSocket ws, Throwable error) {
                close(session, CloseStatus.SERVER_ERROR);
            }
        };
        WebSocket upstream = client.newWebSocketBuilder()
                .header("X-User-Id", userId)
                .connectTimeout(Duration.ofSeconds(5))
                .buildAsync(adapterWs(), listener)
                .join();
        upstreams.put(session, upstream);
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) {
        WebSocket upstream = upstreams.get(session);
        if (upstream != null) {
            upstream.sendText(message.getPayload(), true);
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        WebSocket upstream = upstreams.remove(session);
        if (upstream != null) {
            upstream.abort();
        }
    }

    private void close(WebSocketSession session, CloseStatus status) {
        try {
            session.close(status);
        } catch (Exception ignored) {
            // 已断开的会话再关一次是良性的
        }
    }
}
