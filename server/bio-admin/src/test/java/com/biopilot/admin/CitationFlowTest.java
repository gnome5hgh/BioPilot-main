package com.biopilot.admin;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

import com.biopilot.common.oss.core.MinioTemplate;
import com.biopilot.common.web.http.AgentInternalClient;
import java.nio.charset.StandardCharsets;
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
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;

/** 引用库平台能力：加入/列表/格式化/导出/移出/删除论文连带清理/用户隔离。 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "spring.datasource.url=jdbc:mysql://127.0.0.1:3307/biopilot_test"
                        + "?useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Shanghai",
        })
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class CitationFlowTest {

    @Autowired
    TestRestTemplate rest;

    @Autowired
    JdbcTemplate jdbc;

    @MockBean
    MinioTemplate minio;

    @MockBean
    AgentInternalClient internal;

    private record Session(String token, long userId) {
    }

    @BeforeEach
    void ensureTables() {
        jdbc.execute("DROP TABLE IF EXISTS bio_citation");
        jdbc.execute("DROP TABLE IF EXISTS bio_file");
        jdbc.execute("DROP TABLE IF EXISTS bio_oss_gc");
        jdbc.execute("CREATE TABLE IF NOT EXISTS bio_file ("
                + "id VARCHAR(64) NOT NULL, user_id VARCHAR(191) NOT NULL,"
                + "kind VARCHAR(16) NOT NULL, name VARCHAR(255) NOT NULL,"
                + "name_key VARCHAR(255) COLLATE utf8mb4_0900_bin NULL,"
                + "oss_key VARCHAR(500) NOT NULL, size_bytes BIGINT NOT NULL DEFAULT 0,"
                + "content_type VARCHAR(120) NULL, sha256 CHAR(64) NULL,"
                + "version BIGINT NOT NULL DEFAULT 1, source VARCHAR(16) NULL,"
                + "run_id VARCHAR(64) NULL, conversation_id VARCHAR(64) NULL,"
                + "title VARCHAR(500) NULL, authors VARCHAR(1000) NULL,"
                + "year VARCHAR(10) NULL, journal VARCHAR(300) NULL,"
                + "kb_enabled TINYINT NULL, indexed INTEGER NULL,"
                + "index_status VARCHAR(20) NULL, index_error VARCHAR(500) NULL,"
                + "indexed_at VARCHAR(40) NULL, chunk_count INT NULL,"
                + "citation_id VARCHAR(64) NULL, created_at VARCHAR(40) NOT NULL,"
                + "updated_at VARCHAR(40) NULL, seq BIGINT NOT NULL AUTO_INCREMENT,"
                + "PRIMARY KEY (id), UNIQUE KEY uk_file_seq (seq),"
                + "UNIQUE KEY uk_file_name (user_id, name_key),"
                + "KEY idx_file_user_kind (user_id, kind, seq),"
                + "KEY idx_file_kb (user_id, kind, kb_enabled, index_status))");
        jdbc.execute("CREATE TABLE IF NOT EXISTS bio_oss_gc ("
                + "id BIGINT NOT NULL AUTO_INCREMENT, oss_key VARCHAR(500) NOT NULL,"
                + "reason VARCHAR(32) NOT NULL, attempts INT NOT NULL DEFAULT 0,"
                + "next_at VARCHAR(40) NULL, created_at VARCHAR(40) NOT NULL,"
                + "PRIMARY KEY (id), UNIQUE KEY uk_oss_gc_key (oss_key))");
        jdbc.execute("CREATE TABLE IF NOT EXISTS bio_citation ("
                + "id VARCHAR(64) NOT NULL, user_id VARCHAR(191) NOT NULL,"
                + "cite_key VARCHAR(64) NOT NULL, entry_type VARCHAR(32) NOT NULL DEFAULT 'article',"
                + "title VARCHAR(500) NOT NULL, authors VARCHAR(1000) NOT NULL DEFAULT '',"
                + "year VARCHAR(10) NOT NULL DEFAULT '', journal VARCHAR(300) NOT NULL DEFAULT '',"
                + "volume VARCHAR(40) NULL, pages VARCHAR(60) NULL, doi VARCHAR(200) NULL,"
                + "fields_json MEDIUMTEXT NULL, source VARCHAR(20) NOT NULL,"
                + "created_at VARCHAR(40) NOT NULL, seq BIGINT NOT NULL AUTO_INCREMENT,"
                + "PRIMARY KEY (id), UNIQUE KEY uk_citation_seq (seq),"
                + "UNIQUE KEY uk_citation_user_key (user_id, cite_key),"
                + "KEY idx_citation_user (user_id))");
        when(minio.getObject(anyString()))
                .thenReturn("正文".getBytes(StandardCharsets.UTF_8));
    }

    @AfterEach
    void clean() {
        jdbc.execute("DROP TABLE IF EXISTS bio_citation");
        jdbc.execute("DROP TABLE IF EXISTS bio_file");
        jdbc.execute("DROP TABLE IF EXISTS bio_oss_gc");
        jdbc.execute("TRUNCATE TABLE sys_user");
        jdbc.execute("TRUNCATE TABLE sys_login_log");
        jdbc.execute("TRUNCATE TABLE sys_user_role");
    }

    @Test
    @Order(1)
    void add_list_format_export_remove() {
        Session user = login("citation-user");
        registerPaper(user, "p1", "Attention Is All You Need");

        Map<String, Object> added = post(user, "/api/v1/citations/from-paper",
                Map.of("paper_id", "p1"));
        Map<String, Object> result = (Map<String, Object>) added.get("result");
        String key = (String) result.get("key");
        assertThat(key).isNotBlank();

        List<Map<String, Object>> entries = list(user);
        assertThat(entries).hasSize(1);
        assertThat(entries.get(0).get("title")).isEqualTo("Attention Is All You Need");

        Map<String, Object> formatted = post(user, "/api/v1/citations/format",
                Map.of("keys", List.of(key), "style", "author-year"));
        assertThat((String) formatted.get("text")).contains("Attention Is All You Need");

        Map<String, Object> exported = get(user, "/api/v1/citations/export");
        assertThat((String) exported.get("text")).startsWith("@article{" + key);

        Map<String, Object> removed = delete(user, "/api/v1/citations/by-paper/p1");
        assertThat(removed.get("removed")).isEqualTo(true);
        assertThat(list(user)).isEmpty();
        assertThat(citationIdOf("p1")).isNull();
    }

    @Test
    @Order(2)
    void removing_entry_clears_pointer_and_keeps_paper() {
        Session user = login("citation-remove");
        registerPaper(user, "p2", "A Second Paper Title");

        Map<String, Object> added = post(user, "/api/v1/citations/from-paper",
                Map.of("paper_id", "p2"));
        String key = (String) ((Map<String, Object>) added.get("result")).get("key");

        Map<String, Object> removed = delete(user, "/api/v1/citations/" + key);
        assertThat(removed.get("removed")).isEqualTo(true);
        assertThat(list(user)).isEmpty();
        assertThat(citationIdOf("p2")).isNull();
        assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM bio_file WHERE kind='paper' AND id='p2'",
                Integer.class)).isEqualTo(1);
    }

    @Test
    @Order(3)
    void deleting_paper_removes_entry() {
        Session user = login("citation-delete-paper");
        registerPaper(user, "p3", "A Third Paper Title");
        post(user, "/api/v1/citations/from-paper", Map.of("paper_id", "p3"));
        assertThat(list(user)).hasSize(1);

        delete(user, "/api/v1/papers/p3");
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM bio_citation",
                Integer.class)).isZero();
    }

    @Test
    @Order(4)
    void citations_are_isolated_per_user() {
        Session owner = login("citation-owner");
        Session other = login("citation-other");
        registerPaper(owner, "p4", "Owner Only Paper Title");
        post(owner, "/api/v1/citations/from-paper", Map.of("paper_id", "p4"));

        assertThat(list(owner)).hasSize(1);
        assertThat(list(other)).isEmpty();
    }

    private void registerPaper(Session user, String paperId, String title) {
        HttpHeaders headers = authHeaders(user.token());
        headers.setContentType(org.springframework.http.MediaType.APPLICATION_JSON);
        Map<String, Object> body = Map.of(
                "oss_key", "users/" + user.userId() + "/papers/" + paperId + "/paper.pdf",
                "file_name", paperId + ".pdf",
                "title", title,
                "authors", "Doe, John",
                "year", "2024",
                "journal", "Test Journal");
        ResponseEntity<Map> response = rest.exchange("/api/v1/papers/" + paperId,
                HttpMethod.PUT, new HttpEntity<>(body, headers), Map.class);
        assertThat(response.getStatusCode().value()).isEqualTo(200);
    }

    private String citationIdOf(String paperId) {
        List<String> ids = jdbc.queryForList(
                "SELECT citation_id FROM bio_file WHERE kind='paper' AND id=?",
                String.class, paperId);
        return ids.isEmpty() ? null : ids.get(0);
    }

    private Session login(String userName) {
        rest.postForEntity("/api/v1/auth/register",
                Map.of("userName", userName, "password", "secret123", "nickName", userName), Map.class);
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

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> list(Session user) {
        return (List<Map<String, Object>>) get(user, "/api/v1/citations").get("entries");
    }

    private Map<String, Object> get(Session user, String path) {
        ResponseEntity<Map> response = rest.exchange(path, HttpMethod.GET,
                new HttpEntity<>(authHeaders(user.token())), Map.class);
        assertThat(response.getStatusCode().value()).isEqualTo(200);
        return response.getBody();
    }

    private Map<String, Object> post(Session user, String path, Map<String, Object> body) {
        HttpHeaders headers = authHeaders(user.token());
        headers.setContentType(org.springframework.http.MediaType.APPLICATION_JSON);
        ResponseEntity<Map> response = rest.exchange(path, HttpMethod.POST,
                new HttpEntity<>(body, headers), Map.class);
        assertThat(response.getStatusCode().value()).isEqualTo(200);
        return response.getBody();
    }

    private Map<String, Object> delete(Session user, String path) {
        ResponseEntity<Map> response = rest.exchange(path, HttpMethod.DELETE,
                new HttpEntity<>(authHeaders(user.token())), Map.class);
        assertThat(response.getStatusCode().value()).isEqualTo(200);
        return response.getBody();
    }
}
