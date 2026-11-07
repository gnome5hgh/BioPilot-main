package com.biopilot.admin;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

import com.biopilot.common.oss.core.MinioTemplate;
import com.biopilot.kb.dto.KbPaperView;
import com.biopilot.kb.service.KbPaperService;
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

/** 平台内部端点：附件取回、分析产物登记，以及清单对引擎状态表的只读渲染。 */
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

    @Autowired
    KbPaperService papers;

    @MockBean
    MinioTemplate minio;

    @BeforeEach
    void ensureTables() {
        // 测试库表结构随实体演进：先删后建，避免存量表缺列导致插入/查询 500
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
                + "kb_enabled TINYINT NULL,"
                + "citation_id VARCHAR(64) NULL, created_at VARCHAR(40) NOT NULL,"
                + "updated_at VARCHAR(40) NULL, seq BIGINT NOT NULL AUTO_INCREMENT,"
                + "PRIMARY KEY (id), UNIQUE KEY uk_file_seq (seq),"
                + "UNIQUE KEY uk_file_name (user_id, name_key),"
                + "KEY idx_file_user_kind (user_id, kind, seq),"
                + "KEY idx_file_kb (user_id, kind, kb_enabled))");
        // 引擎侧索引状态表：唯一落点在引擎，Java 只读（索引状态机的语义由引擎测试覆盖）
        jdbc.execute("CREATE TABLE IF NOT EXISTS bio_rag_paper_status ("
                + "user_id VARCHAR(191) NOT NULL, paper_id VARCHAR(64) NOT NULL,"
                + "index_status VARCHAR(20) NOT NULL, indexed TINYINT NOT NULL DEFAULT 0,"
                + "index_error VARCHAR(500) NULL, indexed_at VARCHAR(40) NULL,"
                + "chunk_count INT NOT NULL DEFAULT 0, updated_at VARCHAR(40) NOT NULL,"
                + "PRIMARY KEY (user_id, paper_id),"
                + "KEY idx_paper_status_state (user_id, index_status))");
        jdbc.execute("CREATE TABLE IF NOT EXISTS bio_oss_gc ("
                + "id BIGINT NOT NULL AUTO_INCREMENT, oss_key VARCHAR(500) NOT NULL,"
                + "reason VARCHAR(32) NOT NULL, attempts INT NOT NULL DEFAULT 0,"
                + "next_at VARCHAR(40) NULL, created_at VARCHAR(40) NOT NULL,"
                + "PRIMARY KEY (id), UNIQUE KEY uk_oss_gc_key (oss_key))");
        jdbc.execute("TRUNCATE TABLE bio_file");
        jdbc.execute("TRUNCATE TABLE bio_rag_paper_status");
        jdbc.execute("TRUNCATE TABLE bio_oss_gc");
        when(minio.getObject(anyString()))
                .thenReturn("PDF-BYTES".getBytes(StandardCharsets.UTF_8));
    }

    private HttpHeaders internalHeaders(String userId) {
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-User-Id", userId);
        headers.setContentType(MediaType.APPLICATION_JSON);
        return headers;
    }

    private void paper(String id, String userId, int kb) {
        String name = id + ".pdf";
        jdbc.update("INSERT INTO bio_file (id, user_id, kind, name, name_key, oss_key,"
                        + " size_bytes, content_type, version, source, title,"
                        + " kb_enabled, created_at, updated_at)"
                        + " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                id, userId, "paper", name, name,
                "users/" + userId + "/papers/" + id + "/" + name,
                10, "application/pdf", 1, "paper", "t", kb,
                "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00");
    }

    private void statusRow(String userId, String paperId, String status,
                           int indexed, int chunks) {
        jdbc.update("INSERT INTO bio_rag_paper_status (user_id, paper_id, index_status,"
                        + " indexed, chunk_count, updated_at) VALUES (?,?,?,?,?,?)",
                userId, paperId, status, indexed, chunks, "2026-01-01T00:00:00+00:00");
    }

    @Test
    void list_renders_status_from_engine_table() {
        paper("p1", "42", 1);
        statusRow("42", "p1", "indexed", 1, 7);
        paper("p2", "42", 1);                    // 已勾选、引擎还没建状态行 → queued
        paper("p3", "42", 0);                    // 未勾选 → 一律按未加入展示
        statusRow("42", "p3", "indexed", 1, 9);  // 残留状态行不影响展示

        Map<String, KbPaperView> byId = new java.util.LinkedHashMap<>();
        for (KbPaperView view : papers.list(42L, "all")) {
            byId.put(view.id(), view);
        }

        assertThat(byId.get("p1").indexStatus()).isEqualTo("indexed");
        assertThat(byId.get("p1").chunkCount()).isEqualTo(7);
        assertThat(byId.get("p2").indexStatus()).isEqualTo("queued");
        assertThat(byId.get("p3").indexStatus()).isEqualTo("not_added");
        assertThat(byId.get("p3").chunkCount()).isZero();
    }

    @Test
    void attachment_is_scoped_to_owner() {
        paper("p1", "42", 0);

        ResponseEntity<byte[]> owned = rest.exchange(
                "/internal/attachments/paper/p1", HttpMethod.GET,
                new HttpEntity<>(internalHeaders("42")), byte[].class);
        assertThat(owned.getStatusCode().value()).isEqualTo(200);
        assertThat(owned.getBody()).isEqualTo("PDF-BYTES".getBytes(StandardCharsets.UTF_8));
        assertThat(owned.getHeaders().getFirst("X-File-Name")).isEqualTo("p1.pdf");

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
                "SELECT COUNT(*) FROM bio_file WHERE kind='artifact' AND name='volcano.png'",
                Integer.class)).isEqualTo(2);
    }
}
