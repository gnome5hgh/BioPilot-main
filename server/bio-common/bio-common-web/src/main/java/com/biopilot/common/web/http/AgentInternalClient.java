package com.biopilot.common.web.http;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
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

    @Value("${biopilot.adapter-base}")
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

    /** 内部端点的一次调用结果：状态码 + 原始响应体（调用方决定如何回传）。 */
    public record InternalResponse(int status, String body) {
    }

    /**
     * 同步 POST 内部端点：需要拿上游结果决定后续动作（如删户）时使用。
     *
     * @param path   适配层路径（以 `/internal/` 开头）。
     * @param userId 调用者归属用户。
     * @param body   请求体。
     * @return 上游状态码与响应体；网络错误/构造失败返回 {@code null}，由调用方降级。
     */
    public InternalResponse postSync(String path, long userId, Map<String, Object> body) {
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
            HttpResponse<String> resp = client.send(builder.build(),
                    HttpResponse.BodyHandlers.ofString());
            return new InternalResponse(resp.statusCode(), resp.body());
        } catch (Exception e) {
            log.warn("内部调用失败 {}: {}", path, e.getMessage());
            return null;
        }
    }

    /**
     * 同步 GET 内部端点；失败返回空 Map（调用方按缺省值降级，不因引擎不可达报错）。
     *
     * @param path    适配层路径（以 `/internal/` 开头）。
     * @param userId  归属用户。
     * @param timeout 单次调用超时。
     * @return 解析后的 JSON 对象；网络错误/非 2xx/解析失败时为空 Map。
     */
    public Map<String, Object> get(String path, long userId, Duration timeout) {
        try {
            HttpRequest.Builder builder = HttpRequest.newBuilder()
                    .uri(URI.create(adapterBase + path))
                    .timeout(timeout)
                    .header("X-User-Id", String.valueOf(userId))
                    .GET();
            if (internalToken != null && !internalToken.isBlank()) {
                builder.header("X-Internal-Token", internalToken);
            }
            HttpResponse<String> resp = client.send(builder.build(),
                    HttpResponse.BodyHandlers.ofString());
            if (resp.statusCode() >= 300) {
                log.warn("内部读取失败 {} status={} body={}", path,
                        resp.statusCode(), resp.body());
                return Map.of();
            }
            return mapper.readValue(resp.body(),
                    new TypeReference<Map<String, Object>>() { });
        } catch (Exception e) {
            log.warn("内部读取异常 {}: {}", path, e.getMessage());
            return Map.of();
        }
    }

    /** 知识库运行时信息（collection/embedding/running/last_run）；不可达时返回空 Map。 */
    public Map<String, Object> kbRuntime(long userId) {
        return get("/internal/kb/runtime", userId, Duration.ofSeconds(2));
    }

    /** 唤醒索引器：状态已由 Java 在数据库里写好，这里只触发一次扫描。 */
    public void kbSync(long userId) {
        post("/internal/kb/sync", userId, Map.of());
    }

    /**
     * 触发一次到期的定时任务（Python 侧立即返回、后台执行）。
     *
     * @param userId         归属用户。
     * @param taskId         任务 id（引擎按它去重）。
     * @param conversationId 归属会话。
     * @param task           任务文本。
     * @param name           任务名（仅用于日志）。
     */
    public void runSchedule(long userId, String taskId, String conversationId,
                            String task, String name) {
        post("/internal/schedule/run", userId, Map.of(
                "task_id", taskId == null ? "" : taskId,
                "conversation_id", conversationId == null ? "" : conversationId,
                "task", task == null ? "" : task,
                "name", name == null ? "" : name));
    }
}
