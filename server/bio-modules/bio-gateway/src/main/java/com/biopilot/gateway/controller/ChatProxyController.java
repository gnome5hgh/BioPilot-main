package com.biopilot.gateway.controller;

import com.biopilot.gateway.web.AgentRelay;
import jakarta.servlet.http.HttpServletRequest;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;
import org.springframework.web.bind.annotation.PathVariable;

/** 对话与会话：SSE 对话流、确认回传、历史回放、上下文用量、会话删除。 */
@RestController
@RequestMapping("/api/v1")
public class ChatProxyController {

    private final AgentRelay relay;

    public ChatProxyController(AgentRelay relay) {
        this.relay = relay;
    }

    /** 确认决定回传：透传到适配层 /chat/confirm（唤醒等待中的 run）。 */
    @PostMapping("/chat/confirm")
    public ResponseEntity<String> chatConfirm(@RequestBody String body) {
        return relay.post("/chat/confirm", body);
    }

    /** 删除会话（bio_message 行 + bio_agent_state 行，引擎侧归属双条件）。 */
    @DeleteMapping("/conversations/{conversationId}")
    public ResponseEntity<String> chatSessionDelete(@PathVariable String conversationId) {
        return relay.delete("/chat/session?conversation_id=" + encode(conversationId));
    }

    /** 上下文用量分解：前端悬停面板数据源。 */
    @GetMapping("/conversations/{conversationId}/context-usage")
    public ResponseEntity<String> chatContextUsage(@PathVariable String conversationId) {
        return relay.get("/chat/context-usage?conversation_id=" + encode(conversationId));
    }

    /** 会话历史回放：user/assistant 两条腿，供点击会话后回显。 */
    @GetMapping("/conversations/{conversationId}/messages")
    public ResponseEntity<String> chatHistory(@PathVariable String conversationId) {
        return relay.get("/chat/history?conversation_id=" + encode(conversationId));
    }

    /** 对话主入口：SSE 流式转发（帧节奏由上游决定）。 */
    @PostMapping(value = "/chat/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public ResponseEntity<StreamingResponseBody> chatStream(
            @RequestBody String body, HttpServletRequest request) {
        return relay.stream(body, request.getHeader("X-Conversation-Id"));
    }

    private static String encode(String value) {
        return URLEncoder.encode(value == null ? "" : value, StandardCharsets.UTF_8);
    }
}
