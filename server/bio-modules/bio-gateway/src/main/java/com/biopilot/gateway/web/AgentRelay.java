package com.biopilot.gateway.web;

import cn.dev33.satoken.stp.StpUtil;
import com.biopilot.common.web.http.SseRelay;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

/**
 * 浏览器 → Python 适配层的唯一转发通道。
 *
 * <p>信任边界：登录态里的 userId 即真相，经 {@code X-User-Id} 头透传；适配层
 * 不做二次鉴权（只监听回环/内网）。所有透传端点共用同一个 HttpClient，集中维护
 * 协议版本、超时与错误降级语义。</p>
 */
@Component
public class AgentRelay {

    private static final String UNREACHABLE = "{\"code\":502,\"msg\":\"适配层不可达\"}";

    /** 适配层地址：只允许回环/内网（与适配层监听约束同侧）。 */
    @Value("${biopilot.adapter-base}")
    private String adapterBase;

    // 锁死 HTTP/1.1：默认的 h2c 升级头（Upgrade/HTTP2-Settings）会让 uvicorn 按协议
    // 升级处理并吞掉请求体，所有带 body 的转发（对话/上传）都会变成空体
    private final HttpClient client = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    /** GET 透传（登录态 userId 自动带出）。 */
    public ResponseEntity<String> get(String path) {
        return send("GET", path, null);
    }

    /** POST 透传（JSON body）。 */
    public ResponseEntity<String> post(String path, String body) {
        return send("POST", path, body);
    }

    /** DELETE 透传。 */
    public ResponseEntity<String> delete(String path) {
        return send("DELETE", path, null);
    }

    private ResponseEntity<String> send(String method, String path, String body) {
        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create(adapterBase + path))
                .header("X-User-Id", StpUtil.getLoginIdAsString());
        switch (method) {
            case "GET" -> builder.GET();
            case "DELETE" -> builder.DELETE();
            default -> builder
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(body == null ? "" : body));
        }
        try {
            HttpResponse<String> resp = client.send(builder.build(),
                    HttpResponse.BodyHandlers.ofString());
            return ResponseEntity.status(resp.statusCode())
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(resp.body());
        } catch (Exception e) {
            return unreachable();
        }
    }

    /**
     * 对话流透传：逐块转发并立即 flush，代理不缓冲不重组。
     *
     * <p>进入流之前被适配层拒绝时（429 配额 / 422 缺参 / 装配 500），JSON 错误体
     * 不是 SSE 帧，必须如实带状态码透传，否则前端按 200 解析出空气泡。</p>
     *
     * Args:
     *     body: 对话请求体。
     *     conversationId: 归属会话（可为空，引擎负责生成）。
     *
     * Returns:
     *     流式响应；适配层不可达时返回 502 与一条 error 帧。
     */
    public ResponseEntity<StreamingResponseBody> stream(String body, String conversationId) {
        HttpRequest upstream = HttpRequest.newBuilder()
                .uri(URI.create(adapterBase + "/chat/stream"))
                .header("Content-Type", "application/json")
                .header("X-User-Id", StpUtil.getLoginIdAsString())
                .header("X-Conversation-Id", conversationId == null ? "" : conversationId)
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();
        // 无超时：SSE 长连接的生命周期由两端管理（心跳保活），代理不设应用层超时
        HttpResponse<java.io.InputStream> upstreamResp;
        try {
            upstreamResp = client.send(upstream, HttpResponse.BodyHandlers.ofInputStream());
        } catch (Exception e) {
            StreamingResponseBody errStream = out -> {
                try {
                    out.write("{\"type\":\"error\",\"text\":\"适配层不可达，请稍后重试\"}"
                            .getBytes(StandardCharsets.UTF_8));
                } catch (java.io.IOException ignored) {
                    // 客户端已断开：无需补救
                }
            };
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(errStream);
        }

        if (upstreamResp.statusCode() != 200) {
            String errBody;
            try {
                errBody = new String(upstreamResp.body().readAllBytes(), StandardCharsets.UTF_8);
            } catch (java.io.IOException e) {
                errBody = "{\"code\":502,\"msg\":\"适配层响应读取失败\"}";
            }
            final String errPayload = errBody;
            StreamingResponseBody errStream = out -> {
                out.write(errPayload.getBytes(StandardCharsets.UTF_8));
                out.flush();
            };
            return ResponseEntity.status(upstreamResp.statusCode())
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(errStream);
        }

        java.io.InputStream upstreamBody = upstreamResp.body();
        StreamingResponseBody stream = out -> {
            try (upstreamBody) {
                SseRelay.pump(upstreamBody, out);
            }
        };
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .header("Cache-Control", "no-cache")
                .header("X-Accel-Buffering", "no")
                .body(stream);
    }

    private ResponseEntity<String> unreachable() {
        return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .contentType(MediaType.APPLICATION_JSON)
                .body(UNREACHABLE);
    }
}
