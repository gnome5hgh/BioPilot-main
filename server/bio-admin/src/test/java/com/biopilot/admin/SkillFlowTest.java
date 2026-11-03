package com.biopilot.admin;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.when;

import com.biopilot.common.oss.core.MinioTemplate;
import com.biopilot.common.web.http.AgentInternalClient;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;

/**
 * 技能中心平台能力：安装/列表/详情/启停/删除、用户隔离、标准包准入与内部取包。
 *
 * <p>一致性断言：安装后行与对象同时存在；删除后行先删、对象随后删；准入失败不产生行。</p>
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "spring.datasource.url=jdbc:mysql://127.0.0.1:3307/biopilot_test"
                        + "?useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Shanghai",
        })
class SkillFlowTest {

    @Autowired
    TestRestTemplate rest;

    @Autowired
    JdbcTemplate jdbc;

    @MockBean
    MinioTemplate minio;

    @MockBean
    AgentInternalClient internal;

    /** 模拟 OSS 对象存储（key → bytes），用于校验对象与行的写入顺序。 */
    private final Map<String, byte[]> objects = new ConcurrentHashMap<>();

    @BeforeEach
    void setUp() {
        jdbc.execute("DROP TABLE IF EXISTS bio_skill");
        jdbc.execute("CREATE TABLE IF NOT EXISTS bio_skill ("
                + "id BIGINT NOT NULL AUTO_INCREMENT, user_id VARCHAR(191) NOT NULL,"
                + "name VARCHAR(64) NOT NULL, description VARCHAR(2000) NOT NULL DEFAULT '',"
                + "version VARCHAR(64) NOT NULL DEFAULT '', source VARCHAR(16) NOT NULL,"
                + "source_url VARCHAR(1024) NULL, source_ref VARCHAR(256) NULL,"
                + "source_sha VARCHAR(64) NULL, oss_key VARCHAR(512) NOT NULL,"
                + "content_sha VARCHAR(64) NOT NULL, enabled TINYINT NOT NULL DEFAULT 1,"
                + "installed_at VARCHAR(40) NOT NULL, PRIMARY KEY (id),"
                + "UNIQUE KEY uk_skill_user_name (user_id, name), KEY idx_skill_user (user_id))");
        objects.clear();
        doAnswer(invocation -> {
            objects.put(invocation.getArgument(0), invocation.getArgument(1));
            return null;
        }).when(minio).putObject(anyString(), any(byte[].class), anyString());
        doAnswer(invocation -> {
            objects.remove(invocation.getArgument(0));
            return null;
        }).when(minio).removeObject(anyString());
        when(minio.getObject(anyString()))
                .thenAnswer(invocation -> objects.get(invocation.getArgument(0)));
    }

    @AfterEach
    void clean() {
        jdbc.execute("DROP TABLE IF EXISTS bio_skill");
        jdbc.execute("TRUNCATE TABLE sys_user");
        jdbc.execute("TRUNCATE TABLE sys_login_log");
        jdbc.execute("TRUNCATE TABLE sys_user_role");
    }

    @Test
    void install_list_detail_toggle_delete() {
        Session user = login("skill-owner");
        install(user, "demo-skill");

        List<Map<String, Object>> skills = list(user);
        assertThat(skills).hasSize(1);
        assertThat(skills.get(0).get("name")).isEqualTo("demo-skill");
        assertThat(skills.get(0).get("enabled")).isEqualTo(true);

        // 一致性：行与 OSS 对象同时存在，对象键按 users/<uid>/skills/<name>/<sha>.zip 组织
        Map<String, Object> row = jdbc.queryForMap(
                "SELECT user_id, oss_key, content_sha FROM bio_skill WHERE name='demo-skill'");
        assertThat(String.valueOf(row.get("user_id"))).isEqualTo(String.valueOf(user.userId()));
        String ossKey = String.valueOf(row.get("oss_key"));
        assertThat(ossKey).startsWith("users/" + user.userId() + "/skills/demo-skill/")
                .endsWith(".zip");
        assertThat(objects).containsKey(ossKey);
        assertThat(String.valueOf(row.get("content_sha"))).hasSize(64);

        Map<String, Object> detail = get(user, "/api/v1/skill/demo-skill");
        assertThat(String.valueOf(((Map<?, ?>) detail.get("skill")).get("content")))
                .contains("演示正文");

        Map<String, Object> toggled = post(user, "/api/v1/skill/demo-skill/toggle",
                Map.of("enabled", false));
        assertThat(((Map<?, ?>) toggled.get("skill")).get("enabled")).isEqualTo(false);
        assertThat(jdbc.queryForObject(
                "SELECT enabled FROM bio_skill WHERE name='demo-skill'", Integer.class)).isZero();

        delete(user, "/api/v1/skill/demo-skill");
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM bio_skill", Integer.class)).isZero();
        assertThat(objects).doesNotContainKey(ossKey);   // 先删行、再删对象
    }

    @Test
    void skills_are_isolated_per_user() {
        Session owner = login("skill-owner-2");
        Session other = login("skill-other");
        install(owner, "private-skill");

        assertThat(list(owner)).hasSize(1);
        assertThat(list(other)).isEmpty();

        ResponseEntity<Map> forbidden = rest.exchange("/api/v1/skill/private-skill",
                HttpMethod.GET, new HttpEntity<>(authHeaders(other.token())), Map.class);
        assertThat(forbidden.getStatusCode().value()).isEqualTo(404);
    }

    @Test
    void duplicate_install_rejected_without_partial_state() {
        Session user = login("skill-duplicate");
        install(user, "dup-skill");
        String stagingId = inspect(user, "dup-skill", false);

        ResponseEntity<Map> conflict = rest.exchange("/api/v1/skill/install",
                HttpMethod.POST,
                new HttpEntity<>(Map.of("stagingId", stagingId),
                        jsonHeaders(user.token())), Map.class);
        assertThat(conflict.getStatusCode().value()).isEqualTo(409);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM bio_skill", Integer.class)).isEqualTo(1);
    }

    @Test
    void tools_py_package_rejected() {
        Session user = login("skill-code");
        String stagingId = inspect(user, "code-skill", true);

        // 预览阶段即拒绝
        assertThat(stagingId).isNull();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM bio_skill", Integer.class)).isZero();
        assertThat(objects).isEmpty();
    }

    @Test
    void update_rejected_for_archive_source() {
        Session user = login("skill-update");
        install(user, "archive-skill");
        ResponseEntity<Map> response = rest.exchange("/api/v1/skill/archive-skill/update",
                HttpMethod.POST, new HttpEntity<>(jsonHeaders(user.token())), Map.class);
        assertThat(response.getStatusCode().value()).isEqualTo(422);
    }

    @Test
    void internal_package_served_only_to_owner() {
        Session owner = login("skill-internal");
        Session other = login("skill-internal-other");
        install(owner, "inner-skill");

        HttpHeaders headers = new HttpHeaders();
        headers.set("X-User-Id", String.valueOf(owner.userId()));
        ResponseEntity<byte[]> ok = rest.exchange("/internal/skills/inner-skill/package",
                HttpMethod.GET, new HttpEntity<>(headers), byte[].class);
        assertThat(ok.getStatusCode().value()).isEqualTo(200);
        assertThat(ok.getHeaders().getFirst("X-Content-Sha")).hasSize(64);
        assertThat(ok.getBody()).isNotEmpty();

        HttpHeaders otherHeaders = new HttpHeaders();
        otherHeaders.set("X-User-Id", String.valueOf(other.userId()));
        ResponseEntity<Map> denied = rest.exchange("/internal/skills/inner-skill/package",
                HttpMethod.GET, new HttpEntity<>(otherHeaders), Map.class);
        assertThat(denied.getStatusCode().value()).isEqualTo(404);
    }

    // ----- helpers -----

    private void install(Session user, String name) {
        String stagingId = inspect(user, name, false);
        assertThat(stagingId).isNotBlank();
        Map<String, Object> response = post(user, "/api/v1/skill/install",
                Map.of("stagingId", stagingId));
        assertThat((List<?>) response.get("skills")).isNotEmpty();
    }

    /** 上传 zip 预览；返回 stagingId（tools.py 包返回 null）。 */
    private String inspect(Session user, String name, boolean withTools) {
        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        ByteArrayResource resource = new ByteArrayResource(skillZip(name, withTools)) {
            @Override
            public String getFilename() {
                return "skill.zip";
            }
        };
        body.add("file", resource);
        HttpHeaders headers = new HttpHeaders();
        headers.set("satoken", user.token());
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);
        ResponseEntity<Map> response = rest.exchange("/api/v1/skill/inspect/upload",
                HttpMethod.POST, new HttpEntity<>(body, headers), Map.class);
        if (response.getStatusCode().value() != 200) {
            assertThat(response.getStatusCode().value()).isEqualTo(422);
            return null;
        }
        return String.valueOf(response.getBody().get("stagingId"));
    }

    private byte[] skillZip(String name, boolean withTools) {
        var buffer = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(buffer)) {
            zip.putNextEntry(new ZipEntry("SKILL.md"));
            zip.write(("---\nname: " + name + "\ndescription: 演示技能\n---\n演示正文")
                    .getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
            if (withTools) {
                zip.putNextEntry(new ZipEntry("tools.py"));
                zip.write("TOOLS = []".getBytes(StandardCharsets.UTF_8));
                zip.closeEntry();
            }
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
        return buffer.toByteArray();
    }

    private record Session(String token, long userId) {
    }

    private Session login(String userName) {
        rest.postForEntity("/api/v1/auth/register",
                Map.of("userName", userName, "password", "secret123", "nickName", userName),
                Map.class);
        ResponseEntity<Map> login = rest.postForEntity("/api/v1/auth/login",
                Map.of("userName", userName, "password", "secret123"), Map.class);
        Map<String, Object> data = (Map<String, Object>) login.getBody().get("data");
        return new Session((String) data.get("token"),
                ((Number) data.get("userId")).longValue());
    }

    private HttpHeaders authHeaders(String token) {
        HttpHeaders headers = new HttpHeaders();
        headers.set("satoken", token);
        return headers;
    }

    private HttpHeaders jsonHeaders(String token) {
        HttpHeaders headers = authHeaders(token);
        headers.setContentType(MediaType.APPLICATION_JSON);
        return headers;
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> list(Session user) {
        return (List<Map<String, Object>>) get(user, "/api/v1/skill").get("skills");
    }

    private Map<String, Object> get(Session user, String path) {
        ResponseEntity<Map> response = rest.exchange(path, HttpMethod.GET,
                new HttpEntity<>(authHeaders(user.token())), Map.class);
        assertThat(response.getStatusCode().value()).isEqualTo(200);
        return response.getBody();
    }

    private Map<String, Object> post(Session user, String path, Map<String, Object> body) {
        ResponseEntity<Map> response = rest.exchange(path, HttpMethod.POST,
                new HttpEntity<>(body, jsonHeaders(user.token())), Map.class);
        assertThat(response.getStatusCode().value()).isEqualTo(200);
        return response.getBody();
    }

    private void delete(Session user, String path) {
        ResponseEntity<Map> response = rest.exchange(path, HttpMethod.DELETE,
                new HttpEntity<>(authHeaders(user.token())), Map.class);
        assertThat(response.getStatusCode().value()).isEqualTo(200);
    }
}
