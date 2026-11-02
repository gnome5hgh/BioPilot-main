package com.biopilot.admin;

import static org.assertj.core.api.Assertions.assertThat;

import com.biopilot.common.core.R;
import java.util.Map;
import org.junit.jupiter.api.AfterEach;
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

/** 真实 HTTP（随机端口容器）走注册/登录/登出/角色隔离全链。

    连 biopilot_test 库（测试 properties 覆盖 DSN）；每个用例后清 sys_user 与
    登录日志，用例互不可见。
*/
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "spring.datasource.url=jdbc:mysql://127.0.0.1:3307/biopilot_test"
                        + "?useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Shanghai",
        })
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class AuthFlowTest {

    @Autowired
    TestRestTemplate rest;

    @Autowired
    JdbcTemplate jdbc;

    @AfterEach
    void clean() {
        jdbc.execute("TRUNCATE TABLE sys_user");
        jdbc.execute("TRUNCATE TABLE sys_login_log");
        jdbc.execute("TRUNCATE TABLE sys_user_role");
    }

    private ResponseEntity<Map> post(String path, Map<String, String> body) {
        return rest.postForEntity(path, body, Map.class);
    }

    @SuppressWarnings("unchecked")
    private String loginAndGetToken(String userName, String password) {
        ResponseEntity<Map> r = post("/api/v1/auth/login", Map.of("userName", userName, "password", password));
        assertThat((Integer) r.getBody().get("code")).isEqualTo(200);
        return (String) ((Map) r.getBody().get("data")).get("token");
    }

    private HttpEntity<Void> authed(String token) {
        HttpHeaders headers = new HttpHeaders();
        headers.set("satoken", token);
        return new HttpEntity<>(headers);
    }

    @Test
    @Order(1)
    void register_login_logout_full_flow() {
        // 注册
        ResponseEntity<Map> reg = post("/api/v1/auth/register",
                Map.of("userName", "student1", "password", "secret123", "nickName", "小张"));
        assertThat((Integer) reg.getBody().get("code")).isEqualTo(200);
        // 重复注册拒绝
        ResponseEntity<Map> dup = post("/api/v1/auth/register",
                Map.of("userName", "student1", "password", "x", "nickName", ""));
        assertThat((Integer) dup.getBody().get("code")).isEqualTo(500);
        // 登录拿 token
        String token = loginAndGetToken("student1", "secret123");
        assertThat(token).isNotBlank();
        // 资料：带 token 可读，且角色是 USER
        ResponseEntity<Map> profile = rest.exchange("/api/v1/users/me", HttpMethod.GET,
                authed(token), Map.class);
        assertThat((Integer) profile.getBody().get("code")).isEqualTo(200);
        assertThat((String) ((Map) profile.getBody().get("data")).get("role")).isEqualTo("USER");
        // 登出后 token 失效
        rest.exchange("/api/v1/auth/logout", HttpMethod.POST, authed(token), Map.class);
        ResponseEntity<Map> after = rest.exchange("/api/v1/users/me", HttpMethod.GET,
                authed(token), Map.class);
        assertThat(after.getStatusCode().value()).isEqualTo(401);
        // 登录日志：成功 1 条 + 登出轮无失败
        Integer ok = jdbc.queryForObject(
                "SELECT COUNT(*) FROM sys_login_log WHERE user_name='student1' AND outcome='success'",
                Integer.class);
        assertThat(ok).isGreaterThanOrEqualTo(1);
    }

    @Test
    @Order(2)
    void login_failure_is_recorded_and_rejected() {
        post("/api/v1/auth/register", Map.of("userName", "student2", "password", "secret123"));
        ResponseEntity<Map> bad = post("/api/v1/auth/login",
                Map.of("userName", "student2", "password", "wrong!"));
        assertThat((Integer) bad.getBody().get("code")).isEqualTo(500);
        Integer failed = jdbc.queryForObject(
                "SELECT COUNT(*) FROM sys_login_log WHERE user_name='student2' AND outcome='failed'",
                Integer.class);
        assertThat(failed).isEqualTo(1);
    }

    @Test
    @Order(3)
    void role_guard_rejects_student_and_admits_admin() {
        post("/api/v1/auth/register", Map.of("userName", "student3", "password", "secret123"));
        String userToken = loginAndGetToken("student3", "secret123");

        // 学生（USER）调管理接口 → 403/失败体
        ResponseEntity<Map> denied = rest.exchange("/api/v1/admin/roles", HttpMethod.GET,
                authed(userToken), Map.class);
        System.out.println("[debug] denied=" + denied.getBody() + " status=" + denied.getStatusCode());
        assertThat(denied.getStatusCode().value()).isEqualTo(403);

        // 提升为 ADMIN（直接改库；角色分配的管理接口在管理端展开）
        jdbc.execute("UPDATE sys_user SET role='ADMIN' WHERE user_name='student3'");
        String adminToken = loginAndGetToken("student3", "secret123");
        ResponseEntity<Map> allowed = rest.exchange("/api/v1/admin/roles", HttpMethod.GET,
                authed(adminToken), Map.class);
        assertThat((Integer) allowed.getBody().get("code")).isEqualTo(200);
    }

    @Test
    @Order(4)
    void unauthenticated_requests_are_rejected() {
        ResponseEntity<Map> noToken = rest.getForEntity("/api/v1/users/me", Map.class);
        System.out.println("[debug] no-token=" + noToken.getBody() + " status=" + noToken.getStatusCode());
        assertThat(noToken.getStatusCode().value()).isEqualTo(401);
        assertThat((Integer) noToken.getBody().get("code")).isEqualTo(401);
    }
}
