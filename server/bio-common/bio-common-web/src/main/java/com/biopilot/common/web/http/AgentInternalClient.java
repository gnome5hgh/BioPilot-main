package com.biopilot.common.web.http;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** 调 Python 适配层内部端点的客户端（只用于 `/internal/*`）。

    与面向浏览器的代理共用同一条信任边界：`X-User-Id` 即真相；配置了
    `biopilot.internal-token` 时额外带 `X-Internal-Token`。索引触发是后台动作，
    失败只记日志，不回滚已落库的业务行。
*/
@Component
public class AgentInternalClient {

    private static final Logger log = LoggerFactory.getLogger(AgentInternalClient.class);

    private final HttpClient client = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(5))
            .build();
    private final ObjectMapper mapper;

    @Value("${biopilot.adapter-base:http://127.0.0.1:8300}")
    private String adapterBase;

    @Value("${biopilot.internal-token:}")
    private String internalToken;

    public AgentInternalClient(ObjectMapper mapper) {
        this.mapper = mapper;
    }

    /** 异步 POST 内部端点；失败只记日志（索引可后台重试）。 */
    public void post(String path, long userId, Map<String, Object> body) {
        try {
            String json = mapper.writeValueAsString(body);
            HttpRequest.Builder builder = HttpRequest.newBuilder()
                    .uri(URI.create(adapterBase + path))
                    .timeout(Duration.ofSeconds(30))
                    .header("Content-Type", "application/json")
                    .header("X-User-Id", String.valueOf(userId))
                    .POST(HttpRequest.BodyPublishers.ofString(json));
            if (internalToken != null && !internalToken.isBlank()) {
                builder.header("X-Internal-Token", internalToken);
            }
            client.sendAsync(builder.build(), HttpResponse.BodyHandlers.ofString())
                    .thenAccept(resp -> {
                        if (resp.statusCode() >= 300) {
                            log.warn("内部调用失败 {} status={} body={}", path,
                                    resp.statusCode(), resp.body());
                        }
                    })
                    .exceptionally(e -> {
                        log.warn("内部调用异常 {}: {}", path, e.getMessage());
                        return null;
                    });
        } catch (Exception e) {
            log.warn("内部调用构造失败 {}: {}", path, e.getMessage());
        }
    }

    public void kbEnqueue(long userId, List<String> paperIds) {
        post("/internal/kb/enqueue", userId, Map.of("paper_ids", paperIds));
    }

    public void kbDetach(long userId, List<String> paperIds) {
        post("/internal/kb/detach", userId, Map.of("paper_ids", paperIds));
    }

    public void kbRetry(long userId, List<String> paperIds) {
        post("/internal/kb/retry", userId, Map.of("paper_ids", paperIds));
    }

    public void kbSync(long userId) {
        post("/internal/kb/sync", userId, Map.of());
    }
}
