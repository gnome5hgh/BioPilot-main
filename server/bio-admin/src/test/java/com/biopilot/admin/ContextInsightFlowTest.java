package com.biopilot.admin;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Order;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestMethodOrder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * 上下文侧栏（读侧）：时间线从 bio_message.meta 重建（含压缩点），组成明细从
 * bio_agent_state（message_ids）+ bio_memory_block + bio_skill（当前启用清单）组装，
 * 只返回三类可展示原文的类目；用户隔离与空态降级。
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "spring.datasource.url=jdbc:mysql://127.0.0.1:3307/biopilot_test"
                        + "?useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Shanghai",
        })
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class ContextInsightFlowTest {

    @Autowired
    TestRestTemplate rest;

    @Autowired
    JdbcTemplate jdbc;

    private record Session(String token, String userId) {
    }

    @BeforeEach
    void cleanOwnRows() {
        // 只清本测试的行（引擎表共享，不能 DROP/TRUNCATE）：会话 id 固定为 conv-* 测试名，
        // 记忆块用固定测试 id、技能用固定测试名——user_id 是雪花号，不能按它清理。
        // bio_skill 的建拆归 SkillFlowTest（每个用例前后 DROP），本类与它的执行顺序不保证，
        // 先 IF NOT EXISTS 兜底建表（DDL 与 SkillFlowTest 保持等价）再清行
        jdbc.execute("CREATE TABLE IF NOT EXISTS bio_skill ("
                + "id BIGINT NOT NULL AUTO_INCREMENT, user_id VARCHAR(191) NOT NULL,"
                + "name VARCHAR(64) NOT NULL, description VARCHAR(2000) NOT NULL DEFAULT '',"
                + "version VARCHAR(64) NOT NULL DEFAULT '', source VARCHAR(16) NOT NULL,"
                + "source_url VARCHAR(1024) NULL, source_ref VARCHAR(256) NULL,"
                + "source_sha VARCHAR(64) NULL, oss_key VARCHAR(512) NOT NULL,"
                + "content_sha VARCHAR(64) NOT NULL, enabled TINYINT NOT NULL DEFAULT 1,"
                + "installed_at VARCHAR(40) NOT NULL, PRIMARY KEY (id),"
                + "UNIQUE KEY uk_skill_user_name (user_id, name), KEY idx_skill_user (user_id))");
        jdbc.execute("DELETE FROM bio_message WHERE agent_id LIKE 'conv-%'");
        jdbc.execute("DELETE FROM bio_agent_state WHERE agent_id LIKE 'conv-%'");
        jdbc.execute("DELETE FROM bio_memory_block WHERE id = 'blk-1'");
        jdbc.execute("DELETE FROM bio_skill WHERE name LIKE 'ctx-skill-%'");
    }

    @AfterEach
    void cleanAgain() {
        cleanOwnRows();
    }

    @Test
    @Order(1)
    void timelineRebuildsAndMarksCompaction() {
        Session user = login("ctx-java-tl");
        String conv = "conv-tl-1";
        insertAgentState(user.userId(), conv, "[]");
        // 三个请求：10000 → 12000（正常增长）→ 6000（骤降 → 压缩点）；末行 meta 无 usage
        insertAssistant(user.userId(), conv,
                metaJson(10000, 500, 4000, "m1"));
        insertAssistant(user.userId(), conv,
                metaJson(12000, 300, null, "m1"));
        insertUserMessage(user.userId(), conv,
                "This session is being continued from a previous conversation that ran out of context. 摘要正文");
        insertAssistant(user.userId(), conv,
                metaJson(6000, 200, null, "m1"));
        insertAssistant(user.userId(), conv, "{\"model\":\"m2\"}");

        Map<String, Object> body = get(user,
                "/api/v1/conversations/" + conv + "/context-timeline");
        List<Map<String, Object>> requests = (List<Map<String, Object>>) body.get("requests");
        assertThat(requests).hasSize(4);
        assertThat(requests.get(0).get("prompt_tokens")).isEqualTo(10000);
        assertThat(requests.get(0).get("cached_tokens")).isEqualTo(4000);
        assertThat(requests.get(0).get("model")).isEqualTo("m1");
        assertThat(requests.get(0).get("compacted")).isEqualTo(false);
        // 骤降 + 摘要位置两个信号都落在第 3 个请求
        assertThat(requests.get(2).get("compacted")).isEqualTo(true);
        // 末行无 usage：四项 token 为 null 而非 0
        assertThat(requests.get(3).get("prompt_tokens")).isNull();
        assertThat(requests.get(3).get("model")).isEqualTo("m2");
    }

    @Test
    @Order(2)
    void compositionAssemblesWindowMessagesAndMemory() {
        Session user = login("ctx-java-cp");
        String conv = "conv-cp-1";
        String systemPrompt = "你是生信科研助手（含行为基座拼接）";
        String id1 = "m-cp-1";
        String id2 = "m-cp-2";
        insertAgentStateWithWindow(user.userId(), conv, systemPrompt, 200000,
                "[\"" + id1 + "\",\"" + id2 + "\"]");
        // 窗口外还有一条（已被压缩驱逐）：composition 不应返回它
        insertMessage(user.userId(), conv, id1, "user", "帮我看下数据", null, null);
        insertMessage(user.userId(), conv, id2, "assistant", "", null,
                "[{\"id\":\"c1\",\"type\":\"function\",\"function\":{\"name\":\"search\",\"arguments\":\"{\\\"q\\\":\\\"RNA\\\"}\"}}]");
        insertMessage(user.userId(), conv, "m-cp-evicted", "user", "窗口外的旧消息", null, null);
        jdbc.update("INSERT INTO bio_memory_block (id, user_id, label, value, `limit`, read_only, version, created_at, updated_at)"
                        + " VALUES (?,?,?,?,?,0,1,?,?)",
                "blk-1", user.userId(), "assistant", "身份块内容", 2000,
                "2026-11-14T00:00:00", "2026-11-14T00:00:00");
        // 技能清单来自 bio_skill 当前启用清单：停用技能不出现
        insertSkill(user.userId(), "ctx-skill-a", "单细胞分析技能", true);
        insertSkill(user.userId(), "ctx-skill-b", "已停用技能", false);

        Map<String, Object> composition = compositionOf(user, conv);
        assertThat(composition.get("mode")).isEqualTo("db");
        assertThat(composition.get("limit")).isEqualTo(200000);
        List<Map<String, Object>> categories =
                (List<Map<String, Object>>) composition.get("categories");
        Map<String, Map<String, Object>> byKey = byKey(categories);
        // 只返回三类可展示原文的类目；system 列有值也不再返回 system_prompt 类目
        // （系统提示词/可派发清单/意图/工具定义四类原文只在引擎进程内组装）
        assertThat(byKey).containsOnlyKeys("skills", "memory", "messages");
        // 技能清单：bio_skill 当前启用条目（停用的不出现）
        List<Map<String, Object>> skillItems =
                (List<Map<String, Object>>) byKey.get("skills").get("items");
        assertThat(skillItems).hasSize(1);
        assertThat(skillItems.get(0).get("label")).isEqualTo("ctx-skill-a");
        assertThat(skillItems.get(0).get("content")).isEqualTo("单细胞分析技能");
        // 窗口内消息逐条（窗口外的驱逐行不出现），tool_calls 展平为 {name, arguments}
        List<Map<String, Object>> msgItems =
                (List<Map<String, Object>>) byKey.get("messages").get("items");
        assertThat(msgItems).hasSize(2);
        assertThat(msgItems.get(0).get("content")).isEqualTo("帮我看下数据");
        List<Map<String, String>> calls =
                (List<Map<String, String>>) msgItems.get(1).get("tool_calls");
        assertThat(calls.get(0).get("name")).isEqualTo("search");
        // 记忆块逐条原文
        List<Map<String, Object>> memItems =
                (List<Map<String, Object>>) byKey.get("memory").get("items");
        assertThat(memItems).hasSize(1);
        assertThat(memItems.get(0).get("content")).isEqualTo("身份块内容");
    }

    @Test
    @Order(3)
    void compositionNullWithoutAgentStateAndIsolation() {
        Session user = login("ctx-java-iso");
        String conv = "conv-iso-1";
        // 会话从未运行过（无 agent_state 行）→ composition null
        assertThat(compositionOf(user, conv)).isNull();
        // 他人会话读不到：timeline 空序列、composition null
        Session other = login("ctx-java-iso-other");
        insertAgentState(user.userId(), conv, "[]");
        insertAssistant(user.userId(), conv, metaJson(1000, 10, null, "m"));
        Map<String, Object> body = get(other,
                "/api/v1/conversations/" + conv + "/context-timeline");
        assertThat((List<?>) body.get("requests")).isEmpty();
        assertThat(compositionOf(other, conv)).isNull();
    }

    @Test
    @Order(4)
    void timelineEmptyForBlankHistory() {
        Session user = login("ctx-java-empty");
        Map<String, Object> body = get(user,
                "/api/v1/conversations/conv-none/context-timeline");
        assertThat((List<?>) body.get("requests")).isEmpty();
    }

    // ---- helpers ----

    private Map<String, Object> compositionOf(Session user, String conv) {
        Map<String, Object> body = get(user,
                "/api/v1/conversations/" + conv + "/context-composition");
        return (Map<String, Object>) body.get("composition");
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> get(Session user, String url) {
        ResponseEntity<Map> resp = rest.exchange(url, HttpMethod.GET,
                new HttpEntity<>(authHeaders(user.token())), Map.class);
        assertThat(resp.getStatusCode().is2xxSuccessful()).isTrue();
        return (Map<String, Object>) resp.getBody().get("data");
    }

    private Map<String, Map<String, Object>> byKey(List<Map<String, Object>> categories) {
        Map<String, Map<String, Object>> byKey = new java.util.HashMap<>();
        for (Map<String, Object> cat : categories) {
            byKey.put((String) cat.get("key"), cat);
        }
        return byKey;
    }

    private String metaJson(int prompt, int completion, Integer cached, String model) {
        String cachedPart = cached == null ? "" : ",\"cached_tokens\":" + cached;
        return "{\"model\":\"" + model + "\",\"usage\":{\"prompt_tokens\":" + prompt
                + ",\"completion_tokens\":" + completion + cachedPart + "}}";
    }

    private void insertSkill(String userId, String name, String description, boolean enabled) {
        jdbc.update("INSERT INTO bio_skill (user_id, name, description, version, source,"
                        + " oss_key, content_sha, enabled, installed_at) VALUES (?,?,?,?,?,?,?,?,?)",
                userId, name, description, "1.0.0", "archive",
                "users/" + userId + "/skills/" + name + ".zip", "sha-" + name,
                enabled ? 1 : 0, "2026-11-14T00:00:00");
    }

    private void insertAgentState(String userId, String conv, String messageIds) {
        jdbc.update("INSERT INTO bio_agent_state (agent_id, name, `system`, model,"
                        + " context_window_limit, message_ids, created_at, user_id)"
                        + " VALUES (?,?,?,?,?,?,?,?)",
                conv, "测试会话", "系统提示词原文", "test-model", 128000,
                messageIds, "2026-11-14T00:00:00", userId);
    }

    private void insertAgentStateWithWindow(String userId, String conv, String system,
                                            int limit, String messageIds) {
        jdbc.update("INSERT INTO bio_agent_state (agent_id, name, `system`, model,"
                        + " context_window_limit, message_ids, created_at, user_id)"
                        + " VALUES (?,?,?,?,?,?,?,?)",
                conv, "测试会话", system, "test-model", limit,
                messageIds, "2026-11-14T00:00:00", userId);
    }

    private void insertAssistant(String userId, String conv, String meta) {
        insertMessage(userId, conv, "m-" + java.util.UUID.randomUUID(), "assistant",
                "回答", meta, null);
    }

    private void insertUserMessage(String userId, String conv, String content) {
        insertMessage(userId, conv, "m-" + java.util.UUID.randomUUID(), "user",
                content, null, null);
    }

    private void insertMessage(String userId, String conv, String id, String role,
                               String content, String meta, String toolCalls) {
        jdbc.update("INSERT INTO bio_message (id, user_id, agent_id, role, content, meta,"
                        + " tool_calls, created_at) VALUES (?,?,?,?,?,?,?,?)",
                id, userId, conv, role, content, meta, toolCalls, "2026-11-14T00:00:00");
    }

    private Session login(String userName) {
        rest.postForEntity("/api/v1/auth/register",
                Map.of("userName", userName, "password", "secret123", "nickName", userName), Map.class);
        ResponseEntity<Map> resp = rest.postForEntity("/api/v1/auth/login",
                Map.of("userName", userName, "password", "secret123"), Map.class);
        Map<String, Object> data = (Map<String, Object>) resp.getBody().get("data");
        return new Session((String) data.get("token"),
                String.valueOf(((Number) data.get("userId")).longValue()));
    }

    private HttpHeaders authHeaders(String token) {
        HttpHeaders headers = new HttpHeaders();
        headers.set("satoken", token);
        headers.setContentType(org.springframework.http.MediaType.APPLICATION_JSON);
        return headers;
    }
}
