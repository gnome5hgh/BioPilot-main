package com.biopilot.admin;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

import com.biopilot.common.oss.core.MinioTemplate;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
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

/** 平台内部端点：索引状态机、附件取回、分析产物登记。 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "spring.datasource.url=jdbc:mysql://127.0.0.1:3307/biopilot_test"
                        + "?useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Shanghai",
        })
class InternalCatalogFlowTest {

    @Autowired
    TestRestTemplate rest;

    @Autowired
    JdbcTemplate jdbc;

    @MockBean
    MinioTemplate minio;

    @BeforeEach
    void ensureTables() {
        jdbc.execute("CREATE TABLE IF NOT EXISTS bio_paper ("
                + "id VARCHAR(64) NOT NULL, user_id VARCHAR(191) NOT NULL,"
                + "title VARCHAR(500) NOT NULL, file_name VARCHAR(255) NULL,"
                + "oss_key VARCHAR(500) NOT NULL, size_bytes BIGINT NOT NULL DEFAULT 0,"
                + "indexed INTEGER NOT NULL DEFAULT 0, kb_enabled TINYINT NOT NULL DEFAULT 0,"
                + "citation_id VARCHAR(64) NULL, authors VARCHAR(1000) NOT NULL DEFAULT '',"
                + "year VARCHAR(10) NOT NULL DEFAULT '', journal VARCHAR(300) NOT NULL DEFAULT '',"
                + "index_status VARCHAR(20) NOT NULL DEFAULT 'not_added',"
                + "index_error VARCHAR(500) NULL, indexed_at VARCHAR(40) NULL,"
                + "chunk_count INT NOT NULL DEFAULT 0, created_at VARCHAR(40) NOT NULL,"
                + "seq BIGINT NOT NULL AUTO_INCREMENT, PRIMARY KEY (id),"
                + "UNIQUE KEY uk_papers_seq (seq), KEY idx_papers_user (user_id))");
        jdbc.execute("DROP TABLE IF EXISTS bio_file_upload");
        jdbc.execute("CREATE TABLE IF NOT EXISTS bio_file_upload ("
                + "id VARCHAR(64) NOT NULL, user_id VARCHAR(191) NOT NULL,"
                + "name VARCHAR(255) NOT NULL, oss_key VARCHAR(500) NOT NULL,"
                + "size_bytes BIGINT NOT NULL DEFAULT 0, content_type VARCHAR(120) NULL,"
                + "source VARCHAR(16) NOT NULL DEFAULT 'upload',"
                + "created_at VARCHAR(40) NOT NULL, PRIMARY KEY (id),"
                + "KEY idx_upload_user (user_id))");
        jdbc.execute("CREATE TABLE IF NOT EXISTS bio_user_file ("
                + "id BIGINT NOT NULL AUTO_INCREMENT, user_id VARCHAR(191) NOT NULL,"
                + "kind VARCHAR(16) NOT NULL, name_key VARCHAR(255) NOT NULL,"
                + "name VARCHAR(255) NOT NULL, ref_id VARCHAR(64) NOT NULL,"
                + "created_at VARCHAR(40) NOT NULL, PRIMARY KEY (id),"
                + "UNIQUE KEY uk_user_file_name (user_id, name_key),"
                + "UNIQUE KEY uk_user_file_ref (kind, ref_id),"
                + "KEY idx_user_file_user (user_id))");
        jdbc.execute("TRUNCATE TABLE bio_paper");
        jdbc.execute("TRUNCATE TABLE bio_file_upload");
        jdbc.execute("TRUNCATE TABLE bio_user_file");
        when(minio.getObject(anyString()))
                .thenReturn("PDF-BYTES".getBytes(StandardCharsets.UTF_8));
    }

    private HttpHeaders internalHeaders(String userId) {
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-User-Id", userId);
        headers.setContentType(MediaType.APPLICATION_JSON);
        return headers;
    }

    private void paper(String id, String userId, int kb, String status, int indexed,
                       int chunks) {
        jdbc.update("INSERT INTO bio_paper (id, user_id, title, file_name, oss_key,"
                        + " size_bytes, indexed, kb_enabled, index_status, chunk_count,"
                        + " created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                id, userId, "t", "a.pdf", "users/" + userId + "/papers/" + id + "/a.pdf",
                10, indexed, kb, status, chunks, "2026-01-01T00:00:00+00:00");
    }

    private Map<String, Object> post(String path, String userId, Object body) {
        ResponseEntity<Map> response = rest.exchange(path, HttpMethod.POST,
                new HttpEntity<>(body, internalHeaders(userId)), Map.class);
        assertThat(response.getStatusCode().value()).isEqualTo(200);
        return response.getBody();
    }

    @Test
    void normalize_converges_state_to_kb_enabled() {
        paper("p1", "42", 1, "not_added", 0, 0);
        paper("p2", "42", 0, "indexed", 1, 9);
        paper("p3", "42", 1, "indexing", 0, 0);

        Map<String, Object> out = post("/internal/kb/normalize", "42",
                Map.of("requeue_indexing", true));

        assertThat(out.get("reset")).isEqualTo(1);
        assertThat(out.get("queued")).isEqualTo(1);
        assertThat(out.get("requeued")).isEqualTo(1);
        assertThat(jdbc.queryForObject(
                "SELECT index_status FROM bio_paper WHERE id='p1'", String.class))
                .isEqualTo("queued");
        assertThat(jdbc.queryForObject(
                "SELECT chunk_count FROM bio_paper WHERE id='p2'", Integer.class))
                .isZero();
        assertThat(jdbc.queryForObject(
                "SELECT index_status FROM bio_paper WHERE id='p3'", String.class))
                .isEqualTo("queued");
    }

    @Test
    void requeue_all_only_touches_enabled_rows() {
        paper("p1", "42", 1, "indexed", 1, 12);
        paper("p2", "42", 0, "not_added", 0, 0);

        Map<String, Object> out = post("/internal/kb/requeue-all", "42", Map.of());

        assertThat(out.get("queued")).isEqualTo(1);
        assertThat(jdbc.queryForObject(
                "SELECT index_status FROM bio_paper WHERE id='p1'", String.class))
                .isEqualTo("queued");
        assertThat(jdbc.queryForObject(
                "SELECT index_status FROM bio_paper WHERE id='p2'", String.class))
                .isEqualTo("not_added");
    }

    @Test
    void indexing_and_result_apply_only_while_enabled() {
        paper("p1", "42", 1, "queued", 0, 0);
        paper("p2", "42", 0, "not_added", 0, 0);

        Map<String, Object> indexed = post("/internal/kb/indexing", "42",
                Map.of("paper_ids", List.of("p1", "p2")));
        assertThat(indexed.get("accepted")).isEqualTo(List.of("p1"));
        assertThat(jdbc.queryForObject(
                "SELECT index_status FROM bio_paper WHERE id='p1'", String.class))
                .isEqualTo("indexing");

        Map<String, Object> applied = post("/internal/kb/result", "42",
                Map.of("results", List.of(
                        Map.of("paper_id", "p1", "ok", true, "chunks", 7,
                                "error", ""))));
        assertThat(((Map<?, ?>) applied.get("applied")).get("p1")).isEqualTo(true);
        assertThat(jdbc.queryForObject(
                "SELECT chunk_count FROM bio_paper WHERE id='p1'", Integer.class))
                .isEqualTo(7);

        // 已经 indexed，不再是 indexing：重复上报不落盘
        Map<String, Object> again = post("/internal/kb/result", "42",
                Map.of("results", List.of(
                        Map.of("paper_id", "p1", "ok", true, "chunks", 9,
                                "error", ""))));
        assertThat(((Map<?, ?>) again.get("applied")).get("p1")).isEqualTo(false);
    }

    @Test
    void result_is_rejected_after_detach() {
        paper("p1", "42", 1, "indexing", 0, 0);
        jdbc.update("UPDATE bio_paper SET kb_enabled=0 WHERE id='p1'");

        Map<String, Object> applied = post("/internal/kb/result", "42",
                Map.of("results", List.of(
                        Map.of("paper_id", "p1", "ok", true, "chunks", 7,
                                "error", ""))));

        assertThat(((Map<?, ?>) applied.get("applied")).get("p1")).isEqualTo(false);
        assertThat(jdbc.queryForObject(
                "SELECT index_status FROM bio_paper WHERE id='p1'", String.class))
                .isEqualTo("indexing");
    }

    @Test
    void attachment_is_scoped_to_owner() {
        paper("p1", "42", 0, "not_added", 0, 0);

        ResponseEntity<byte[]> owned = rest.exchange(
                "/internal/attachments/paper/p1", HttpMethod.GET,
                new HttpEntity<>(internalHeaders("42")), byte[].class);
        assertThat(owned.getStatusCode().value()).isEqualTo(200);
        assertThat(owned.getBody()).isEqualTo("PDF-BYTES".getBytes(StandardCharsets.UTF_8));
        assertThat(owned.getHeaders().getFirst("X-File-Name")).isEqualTo("a.pdf");

        ResponseEntity<byte[]> foreign = rest.exchange(
                "/internal/attachments/paper/p1", HttpMethod.GET,
                new HttpEntity<>(internalHeaders("99")), byte[].class);
        assertThat(foreign.getStatusCode().value()).isEqualTo(404);
    }

    @Test
    void artifact_upload_allows_duplicate_names() {
        for (int i = 0; i < 2; i++) {
            MultiValueMap<String, Object> form = new LinkedMultiValueMap<>();
            form.add("run_id", "run-1");
            form.add("file", new ByteArrayResource("PNG".getBytes(StandardCharsets.UTF_8)) {
                @Override
                public String getFilename() {
                    return "volcano.png";
                }
            });
            HttpHeaders headers = internalHeaders("42");
            headers.setContentType(MediaType.MULTIPART_FORM_DATA);
            ResponseEntity<Map> response = rest.exchange("/internal/files/artifacts",
                    HttpMethod.POST, new HttpEntity<>(form, headers), Map.class);
            assertThat(response.getStatusCode().value()).isEqualTo(200);
            assertThat(response.getBody().get("oss_key").toString())
                    .startsWith("users/42/files/analysis/run-1/");
        }
        assertThat(jdbc.queryForObject(
                "SELECT COUNT(*) FROM bio_file_upload WHERE name='volcano.png'",
                Integer.class)).isEqualTo(2);
    }
}
