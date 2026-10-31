package com.biopilot.admin.controller;

import cn.dev33.satoken.stp.StpUtil;
import com.biopilot.common.core.R;
import jakarta.servlet.http.HttpServletRequest;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

/** Agent 对话代理：把登录用户的 SSE 请求转发到内网 Python 适配层。

    归属传递（信任边界）：登录态里的 userId 即真相，经 X-User-Id 头透传给
    适配层；适配层不做二次鉴权（只监听内网回环）。响应体逐字节流式拷贝——
    SSE 帧的节奏由上游决定，代理不缓冲不重组。
*/
@RestController
@RequestMapping("/agent")
public class AgentProxyController {

    /** 适配层地址：只允许回环/内网（与适配层监听约束同侧）。 */
    private static final String ADAPTER_BASE = "http://127.0.0.1:8300";

    private final HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    /** 确认决定回传：透传到适配层 /chat/confirm（唤醒等待中的 run）。 */
    @PostMapping("/chat/confirm")
    public ResponseEntity<String> chatConfirm(@RequestBody String body) {
        long userId = StpUtil.getLoginIdAsLong();
        HttpRequest upstream = HttpRequest.newBuilder()
                .uri(URI.create(ADAPTER_BASE + "/chat/confirm"))
                .header("Content-Type", "application/json")
                .header("X-User-Id", String.valueOf(userId))
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();
        try {
            HttpResponse<String> resp = client.send(upstream,
                    HttpResponse.BodyHandlers.ofString());
            return ResponseEntity.status(resp.statusCode())
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(resp.body());
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("{\"code\":502,\"msg\":\"适配层不可达\"}");
        }
    }

    /** 论文目录：列表（读 papers 表，user_id 行级过滤）。 */
    @GetMapping("/papers")
    public ResponseEntity<String> papersList() {
        return proxyGet("/papers");
    }

    /** 论文登记（元数据落库，原文由上传方先行落 OSS）。 */
    @PostMapping("/papers/{paperId}")
    public ResponseEntity<String> papersRegister(@PathVariable String paperId,
                                                 @RequestBody String body) {
        long userId = StpUtil.getLoginIdAsLong();
        HttpRequest upstream = HttpRequest.newBuilder()
                .uri(URI.create(ADAPTER_BASE + "/papers/" + paperId))
                .header("Content-Type", "application/json")
                .header("X-User-Id", String.valueOf(userId))
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();
        try {
            HttpResponse<String> resp = client.send(upstream,
                    HttpResponse.BodyHandlers.ofString());
            return ResponseEntity.status(resp.statusCode())
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(resp.body());
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("{\"code\":502,\"msg\":\"适配层不可达\"}");
        }
    }

    /** 论文删除（行→对象删除方向由 Python 侧返回 oss_key）。 */
    @org.springframework.web.bind.annotation.DeleteMapping("/papers/{paperId}")
    public ResponseEntity<String> papersDelete(@PathVariable String paperId) {
        long userId = StpUtil.getLoginIdAsLong();
        HttpRequest upstream = HttpRequest.newBuilder()
                .uri(URI.create(ADAPTER_BASE + "/papers/" + paperId))
                .header("X-User-Id", String.valueOf(userId))
                .DELETE()
                .build();
        try {
            HttpResponse<String> resp = client.send(upstream,
                    HttpResponse.BodyHandlers.ofString());
            return ResponseEntity.status(resp.statusCode())
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(resp.body());
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("{\"code\":502,\"msg\":\"适配层不可达\"}");
        }
    }

    /** 商店/技能读接口透传（Python 侧读 agents/skills 真数据）。 */
    @GetMapping("/store/experts")
    public ResponseEntity<String> storeExperts() {
        return proxyGet("/store/experts");
    }

    @GetMapping("/store/skills")
    public ResponseEntity<String> storeSkills() {
        return proxyGet("/store/skills");
    }

    /** 技能启停（管理动作）：透传切换请求。 */
    @PostMapping("/store/skills/{name}/toggle")
    public ResponseEntity<String> skillToggle(@PathVariable String name,
                                              @RequestBody String body) {
        long userId = StpUtil.getLoginIdAsLong();
        HttpRequest upstream = HttpRequest.newBuilder()
                .uri(URI.create(ADAPTER_BASE + "/store/skills/" + name + "/toggle"))
                .header("Content-Type", "application/json")
                .header("X-User-Id", String.valueOf(userId))
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();
        try {
            HttpResponse<String> resp = client.send(upstream,
                    HttpResponse.BodyHandlers.ofString());
            return ResponseEntity.status(resp.statusCode())
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(resp.body());
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("{\"code\":502,\"msg\":\"适配层不可达\"}");
        }
    }

    private ResponseEntity<String> proxyGet(String path) {
        long userId = StpUtil.getLoginIdAsLong();
        HttpRequest upstream = HttpRequest.newBuilder()
                .uri(URI.create(ADAPTER_BASE + path))
                .header("X-User-Id", String.valueOf(userId))
                .GET()
                .build();
        try {
            HttpResponse<String> resp = client.send(upstream,
                    HttpResponse.BodyHandlers.ofString());
            return ResponseEntity.status(resp.statusCode())
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(resp.body());
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("{\"code\":502,\"msg\":\"适配层不可达\"}");
        }
    }

    @PostMapping(value = "/chat/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public ResponseEntity<StreamingResponseBody> chatStream(
            @RequestBody String body, HttpServletRequest request) {
        long userId = StpUtil.getLoginIdAsLong();
        String conversationId = request.getHeader("X-Conversation-Id");

        HttpRequest upstream = HttpRequest.newBuilder()
                .uri(URI.create(ADAPTER_BASE + "/chat/stream"))
                .header("Content-Type", "application/json")
                .header("X-User-Id", String.valueOf(userId))
                .header("X-Conversation-Id", conversationId == null ? "" : conversationId)
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

        // 无超时：SSE 长连接的生命周期由两端管理（心跳保活），代理不设应用层超时
        HttpResponse<java.io.InputStream> upstreamResp;
        try {
            upstreamResp = client.send(upstream,
                    HttpResponse.BodyHandlers.ofInputStream());
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(write -> {
                        try {
                            write.write(("{\"type\":\"error\",\"text\":\"适配层不可达，请稍后重试\"}")
                                    .getBytes(java.nio.charset.StandardCharsets.UTF_8));
                        } catch (java.io.IOException ignored) {
                            // 客户端已断开：无需补救
                        }
                    });
        }

        java.io.InputStream upstreamBody = upstreamResp.body();
        StreamingResponseBody stream = out -> {
            try (upstreamBody) {
                upstreamBody.transferTo(out);
                out.flush();
            }
        };
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .body(stream);
    }
}
