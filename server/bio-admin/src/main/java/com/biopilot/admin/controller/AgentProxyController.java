package com.biopilot.admin.controller;

import cn.dev33.satoken.annotation.SaCheckRole;
import cn.dev33.satoken.stp.StpUtil;
import com.biopilot.common.core.R;
import com.biopilot.common.web.http.SseRelay;
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
import org.springframework.web.bind.annotation.RequestParam;
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

    /** 适配层地址：只允许回环/内网（与适配层监听约束同侧）。
        容器部署经 biopilot.adapter-base 指向 compose 服务名（env 可覆盖）。 */
    @org.springframework.beans.factory.annotation.Value(
            "${biopilot.adapter-base:http://127.0.0.1:8300}")
    private String adapterBase;

    /** 内部调用共享 token：删户等 /internal/* 端点额外携带。 */
    @org.springframework.beans.factory.annotation.Value("${biopilot.internal-token:}")
    private String internalToken;

    private final com.biopilot.system.service.SysUserService sysUserService;
    private final com.biopilot.catalog.service.PlatformUserDataService platformUserData;
    private final com.biopilot.catalog.service.PaperService papers;

    public AgentProxyController(com.biopilot.system.service.SysUserService sysUserService,
                                com.biopilot.catalog.service.PlatformUserDataService platformUserData,
                                com.biopilot.catalog.service.PaperService papers) {
        this.sysUserService = sysUserService;
        this.platformUserData = platformUserData;
        this.papers = papers;
    }

    // 锁死 HTTP/1.1：默认的 h2c 升级头（Upgrade/HTTP2-Settings）会让 uvicorn 按协议
    // 升级处理并吞掉请求体，所有带 body 的转发（对话/上传）都会变成空体
    private final HttpClient client = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(5))
            .build();

    /** 确认决定回传：透传到适配层 /chat/confirm（唤醒等待中的 run）。 */
    @PostMapping("/chat/confirm")
    public ResponseEntity<String> chatConfirm(@RequestBody String body) {
        long userId = StpUtil.getLoginIdAsLong();
        HttpRequest upstream = HttpRequest.newBuilder()
                .uri(URI.create(adapterBase + "/chat/confirm"))
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

    private ResponseEntity<String> proxyPost(String path, String body) {
        return sendPost(path, body, false);
    }

    /** /internal/* 转发：额外带共享 token（Python 侧内部端点要求）。 */
    private ResponseEntity<String> proxyInternalPost(String path, String body) {
        return sendPost(path, body, true);
    }

    private ResponseEntity<String> sendPost(String path, String body, boolean internal) {
        long userId = StpUtil.getLoginIdAsLong();
        HttpRequest.Builder builder = HttpRequest.newBuilder()
                .uri(URI.create(adapterBase + path))
                .header("Content-Type", "application/json")
                .header("X-User-Id", String.valueOf(userId))
                .POST(HttpRequest.BodyPublishers.ofString(body == null ? "" : body));
        if (internal && internalToken != null && !internalToken.isBlank()) {
            builder.header("X-Internal-Token", internalToken);
        }
        try {
            HttpResponse<String> resp = client.send(builder.build(),
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

    /** 会话级多模型：清单（不含 key）与选择切换，切换下一 run 生效。 */
    @GetMapping("/models")
    public ResponseEntity<String> modelsList() {
        return proxyGet("/models");
    }

    @PostMapping("/models/select")
    public ResponseEntity<String> modelsSelect(@RequestBody String body) {
        return proxyPost("/models/select", body);
    }

    /** 会话列表（左栏）：本用户的会话（标题/时间/消息数），按新→旧。 */
    @GetMapping("/sessions")
    public ResponseEntity<String> sessionsList(
            @org.springframework.web.bind.annotation.RequestParam(defaultValue = "50") int limit) {
        return proxyGet("/sessions?limit=" + Math.max(1, Math.min(limit, 200)));
    }

    /** 删除会话（bio_message 行 + bio_agent_state 行，引擎侧归属双条件）。 */
    @DeleteMapping("/chat/session")
    public ResponseEntity<String> chatSessionDelete(@RequestParam String conversationId) {
        long userId = StpUtil.getLoginIdAsLong();
        HttpRequest upstream = HttpRequest.newBuilder()
                .uri(URI.create(adapterBase + "/chat/session?conversation_id="
                        + java.net.URLEncoder.encode(conversationId, java.nio.charset.StandardCharsets.UTF_8)))
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

    /** 上下文用量分解：前端悬停面板数据源。 */
    @GetMapping("/chat/context-usage")
    public ResponseEntity<String> chatContextUsage(
            @RequestParam String conversationId) {
        return proxyGet("/chat/context-usage?conversation_id="
                + java.net.URLEncoder.encode(conversationId, java.nio.charset.StandardCharsets.UTF_8));
    }

    /** 会话历史回放：user/assistant 两条腿，供点击会话后回显。 */
    @GetMapping("/chat/history")
    public ResponseEntity<String> chatHistory(
            @org.springframework.web.bind.annotation.RequestParam String conversationId) {
        return proxyGet("/chat/history?conversation_id="
                + java.net.URLEncoder.encode(conversationId, java.nio.charset.StandardCharsets.UTF_8));
    }

    /** KB 知识库：论文勾选加入/移出/重试、试检索、分块（状态概览由 Java 自己算）。 */
    @GetMapping("/kb/papers/{paperId}/chunks")
    public ResponseEntity<String> kbPaperChunks(@PathVariable String paperId) {
        // 归属校验留在平台侧：引擎只按 id 读 RAG 索引，不再查 bio_paper
        papers.get(StpUtil.getLoginIdAsLong(), paperId);
        return proxyGet("/kb/papers/" + paperId + "/chunks");
    }

    @PostMapping("/kb/reindex")
    public ResponseEntity<String> kbReindex(
            @RequestParam(defaultValue = "false") boolean force) {
        return proxyPost("/kb/reindex?force=" + force, "{}");
    }

    @PostMapping("/kb/search")
    public ResponseEntity<String> kbSearch(@RequestBody String body) {
        return proxyPost("/kb/search", body);
    }

    /** 终端面板：部署开关与重启（WS 本体由 TerminalRelayHandler 单独转发）。 */
    @GetMapping("/terminal/config")
    public ResponseEntity<String> terminalConfig() {
        return proxyGet("/terminal/config");
    }

    @PostMapping("/terminal/restart")
    public ResponseEntity<String> terminalRestart() {
        return proxyPost("/terminal/restart", "{}");
    }

    /** 设置读/写（ADMIN 专属：响应含带 key 的模型清单，学生不可见）。 */
    @SaCheckRole("ADMIN")
    @GetMapping("/settings")
    public ResponseEntity<String> settingsGet() {
        return proxyGet("/settings");
    }

    @cn.dev33.satoken.annotation.SaCheckRole("ADMIN")
    @org.springframework.web.bind.annotation.PostMapping("/settings")
    public ResponseEntity<String> settingsSet(@RequestBody String body) {
        return proxyPost("/settings", body);
    }

    /** 删户两阶段（管理动作）：标记（停用登录 + 踢下线）+ 物理清理透传。 */
    @SaCheckRole("ADMIN")
    @PostMapping("/admin/users/{targetId}/mark-deleting")
    public ResponseEntity<String> markDeleting(@PathVariable String targetId) {
        // 引擎数据清理前先断掉该账号的会话与登录能力：DELETING 期间不再接新工作
        try {
            StpUtil.kickout(Long.valueOf(targetId));
        } catch (Exception ignored) {
            // 目标本就不在线：kick 语义幂等
        }
        var u = sysUserService.getById(Long.valueOf(targetId));
        if (u != null) {
            u.setStatus("1");
            sysUserService.updateById(u);
        }
        return proxyInternalPost("/internal/users/" + targetId + "/mark-deleting", "{}");
    }

    @SaCheckRole("ADMIN")
    @PostMapping("/admin/users/{targetId}/purge")
    public ResponseEntity<String> purgeUser(@PathVariable String targetId) {
        ResponseEntity<String> upstream =
                proxyInternalPost("/internal/users/" + targetId + "/purge", "{}");
        // 引擎侧清理成功后：先清平台表行与 OSS 对象，最后删账号（先数据后账号）。
        // 平台清理失败时不删账号，管理员可重试，避免留下「账号没了、数据还在」。
        if (upstream.getStatusCode().is2xxSuccessful()) {
            platformUserData.purge(targetId);
            var u = sysUserService.getById(Long.valueOf(targetId));
            if (u != null) {
                sysUserService.deleteById(Long.valueOf(targetId));
            }
        }
        return upstream;
    }

    /** 技能商店（读接口透传，Python 侧读 .biopilot/skills 真数据）。 */
    @GetMapping("/store/skills")
    public ResponseEntity<String> storeSkills() {
        return proxyGet("/store/skills");
    }

    /** 技能启停（管理动作）：透传切换请求。 */
    @SaCheckRole("ADMIN")
    @PostMapping("/store/skills/{name}/toggle")
    public ResponseEntity<String> skillToggle(@PathVariable String name,
                                              @RequestBody String body) {
        long userId = StpUtil.getLoginIdAsLong();
        HttpRequest upstream = HttpRequest.newBuilder()
                .uri(URI.create(adapterBase + "/store/skills/" + name + "/toggle"))
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
                .uri(URI.create(adapterBase + path))
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
                .uri(URI.create(adapterBase + "/chat/stream"))
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
            StreamingResponseBody errStream = write -> {
                try {
                    write.write(("{\"type\":\"error\",\"text\":\"适配层不可达，请稍后重试\"}")
                            .getBytes(java.nio.charset.StandardCharsets.UTF_8));
                } catch (java.io.IOException ignored) {
                    // 客户端已断开：无需补救
                }
            };
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(errStream);
        }

        if (upstreamResp.statusCode() != 200) {
            // 进入流之前就被适配层拒绝（429 配额/422 缺参/装配 500）：JSON 错误体
            // 不是 SSE 帧，必须如实带状态码透传，否则前端按 200 解析出空气泡。
            // 返回类型必须保持 StreamingResponseBody——放宽成通配符会让 Spring
            // 去找 JSON converter 而不是走流式输出（No converter for Lambda）。
            String errBody;
            try {
                errBody = new String(upstreamResp.body().readAllBytes(),
                        java.nio.charset.StandardCharsets.UTF_8);
            } catch (java.io.IOException e) {
                errBody = "{\"code\":502,\"msg\":\"适配层响应读取失败\"}";
            }
            final String errPayload = errBody;
            StreamingResponseBody errStream = out -> {
                out.write(errPayload.getBytes(java.nio.charset.StandardCharsets.UTF_8));
                out.flush();
            };
            return ResponseEntity.status(upstreamResp.statusCode())
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(errStream);
        }
        java.io.InputStream upstreamBody = upstreamResp.body();
        StreamingResponseBody stream = out -> {
            try (upstreamBody) {
                // 逐块转发并立即 flush：SSE 的可见节奏由上游每个帧决定
                SseRelay.pump(upstreamBody, out);
            }
        };
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_EVENT_STREAM)
                .header("Cache-Control", "no-cache")
                .header("X-Accel-Buffering", "no")
                .body(stream);
    }
}
