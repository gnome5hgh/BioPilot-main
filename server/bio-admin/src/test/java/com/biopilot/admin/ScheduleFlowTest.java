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

/** 定时任务定义 CRUD 与用户隔离：真实 HTTP + 真实库表。 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "spring.datasource.url=jdbc:mysql://127.0.0.1:3306/biopilot_test"
                        + "?useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Shanghai",
        })
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class ScheduleFlowTest {

    @Autowired
    TestRestTemplate rest;

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void ensureTable() {
        jdbc.execute("CREATE TABLE IF NOT EXISTS bio_schedule_task ("
                + "id VARCHAR(64) NOT NULL,"
                + "user_id VARCHAR(191) NOT NULL,"
                + "conversation_id VARCHAR(64) NOT NULL,"
                + "name VARCHAR(200) NOT NULL,"
                + "task TEXT NOT NULL,"
                + "interval_minutes INTEGER NOT NULL,"
                + "paused INTEGER NOT NULL DEFAULT 0,"
                + "last_run_at VARCHAR(40) NULL,"
                + "next_run_at VARCHAR(40) NOT NULL,"
                + "created_at VARCHAR(40) NOT NULL,"
                + "PRIMARY KEY (id), KEY idx_sched_user (user_id), KEY idx_sched_next (next_run_at)"
                + ")");
        jdbc.execute("TRUNCATE TABLE bio_schedule_task");
        jdbc.execute("TRUNCATE TABLE sys_user");
        jdbc.execute("TRUNCATE TABLE sys_login_log");
        jdbc.execute("TRUNCATE TABLE sys_user_role");
    }

    @AfterEach
    void clean() {
        jdbc.execute("TRUNCATE TABLE bio_schedule_task");
        jdbc.execute("TRUNCATE TABLE sys_user");
        jdbc.execute("TRUNCATE TABLE sys_login_log");
        jdbc.execute("TRUNCATE TABLE sys_user_role");
    }

    private String tokenFor(String userName) {
        rest.postForEntity("/auth/register",
                Map.of("userName", userName, "password", "secret123", "nickName", userName), Map.class);
        ResponseEntity<Map> login = rest.postForEntity("/auth/login",
                Map.of("userName", userName, "password", "secret123"), Map.class);
        return (String) ((Map) login.getBody().get("data")).get("token");
    }

    private HttpEntity<Object> authed(String token, Object body) {
        HttpHeaders headers = new HttpHeaders();
        headers.set("satoken", token);
        headers.set("Content-Type", "application/json");
        return new HttpEntity<>(body, headers);
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> list(String token) {
        ResponseEntity<Map> response = rest.exchange("/agent/schedules", HttpMethod.GET,
                authed(token, null), Map.class);
        return (List<Map<String, Object>>) response.getBody().get("schedules");
    }

    @Test
    @Order(1)
    void create_list_pause_resume_run_delete() {
        String token = tokenFor("sched-user");
        ResponseEntity<Map> created = rest.exchange("/agent/schedules", HttpMethod.POST,
                authed(token, Map.of(
                        "name", "每周文献巡检",
                        "task", "检索本周新文献",
                        "conversation_id", "conv-1",
                        "interval_minutes", 60)), Map.class);
        assertThat((String) created.getBody().get("status")).isEqualTo("ok");

        List<Map<String, Object>> rows = list(token);
        assertThat(rows).hasSize(1);
        assertThat(rows.get(0).get("name")).isEqualTo("每周文献巡检");
        assertThat(rows.get(0).get("interval_minutes")).isEqualTo(60);
        assertThat(rows.get(0).get("paused")).isEqualTo(0);
        String taskId = (String) rows.get(0).get("id");

        rest.exchange("/agent/schedules/" + taskId + "/pause", HttpMethod.POST,
                authed(token, null), Map.class);
        assertThat(list(token).get(0).get("paused")).isEqualTo(1);

        rest.exchange("/agent/schedules/" + taskId + "/resume", HttpMethod.POST,
                authed(token, null), Map.class);
        assertThat(list(token).get(0).get("paused")).isEqualTo(0);

        ResponseEntity<Map> run = rest.exchange("/agent/schedules/" + taskId + "/run",
                HttpMethod.POST, authed(token, null), Map.class);
        assertThat((String) run.getBody().get("status")).isEqualTo("queued");

        rest.exchange("/agent/schedules/" + taskId, HttpMethod.DELETE,
                authed(token, null), Map.class);
        assertThat(list(token)).isEmpty();
    }

    @Test
    @Order(2)
    void invalid_interval_is_rejected() {
        String token = tokenFor("sched-bad");
        ResponseEntity<Map> created = rest.exchange("/agent/schedules", HttpMethod.POST,
                authed(token, Map.of(
                        "name", "x", "task", "y",
                        "conversation_id", "conv-1", "interval_minutes", 1)), Map.class);
        assertThat(created.getStatusCode().value()).isEqualTo(422);
        assertThat(list(token)).isEmpty();
    }

    @Test
    @Order(3)
    void schedules_are_isolated_per_user() {
        String owner = tokenFor("sched-owner");
        String other = tokenFor("sched-other");
        rest.exchange("/agent/schedules", HttpMethod.POST,
                authed(owner, Map.of(
                        "name", "owner-task", "task", "t",
                        "conversation_id", "conv-owner", "interval_minutes", 60)), Map.class);
        String taskId = (String) list(owner).get(0).get("id");

        assertThat(list(other)).isEmpty();
        ResponseEntity<Map> foreignRun = rest.exchange("/agent/schedules/" + taskId + "/run",
                HttpMethod.POST, authed(other, null), Map.class);
        assertThat(foreignRun.getStatusCode().value()).isEqualTo(404);

        // 别人的删除请求不能动到这一行
        rest.exchange("/agent/schedules/" + taskId, HttpMethod.DELETE,
                authed(other, null), Map.class);
        assertThat(list(owner)).hasSize(1);
    }
}
