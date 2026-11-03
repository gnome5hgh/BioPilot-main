package com.biopilot.admin;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.biopilot.common.oss.core.MinioTemplate;
import com.biopilot.common.web.http.AgentInternalClient;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
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
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;

/** 论文/数据文件/文档三个文件能力的 HTTP 契约与用户隔离（OSS 与引擎调用打桩）。 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "spring.datasource.url=jdbc:mysql://127.0.0.1:3307/biopilot_test"
                        + "?useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Shanghai",
        })
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class CatalogFlowTest {

    @Autowired
    TestRestTemplate rest;

    @Autowired
    JdbcTemplate jdbc;

    @MockBean
    MinioTemplate minio;

    @MockBean
    AgentInternalClient internal;

    @BeforeEach
    void ensureTables() {
        // 测试库表结构随实体演进：先删后建，避免存量表缺列导致插入/查询 500
        jdbc.execute("DROP TABLE IF EXISTS bio_paper");
        jdbc.execute("DROP TABLE IF EXISTS bio_file_upload");
        jdbc.execute("DROP TABLE IF EXISTS bio_document");
        jdbc.execute("DROP TABLE IF EXISTS bio_user_file");
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
        jdbc.execute("CREATE TABLE IF NOT EXISTS bio_file_upload ("
                + "id VARCHAR(64) NOT NULL, user_id VARCHAR(191) NOT NULL,"
                + "name VARCHAR(255) NOT NULL, oss_key VARCHAR(500) NOT NULL,"
                + "size_bytes BIGINT NOT NULL DEFAULT 0, content_type VARCHAR(120) NULL,"
                + "source VARCHAR(16) NOT NULL DEFAULT 'upload',"
                + "created_at VARCHAR(40) NOT NULL, PRIMARY KEY (id),"
                + "KEY idx_upload_user (user_id))");
        jdbc.execute("CREATE TABLE IF NOT EXISTS bio_document ("
                + "id VARCHAR(64) NOT NULL, user_id VARCHAR(191) NOT NULL,"
                + "name VARCHAR(200) NOT NULL, content MEDIUMTEXT NULL,"
                + "oss_key VARCHAR(500) NULL, updated_at VARCHAR(40) NOT NULL,"
                + "seq BIGINT NOT NULL AUTO_INCREMENT, PRIMARY KEY (id),"
                + "UNIQUE KEY uk_documents_seq (seq), KEY idx_documents_user (user_id))");
        jdbc.execute("CREATE TABLE IF NOT EXISTS bio_user_file ("
                + "id BIGINT NOT NULL AUTO_INCREMENT, user_id VARCHAR(191) NOT NULL,"
                + "kind VARCHAR(16) NOT NULL, name_key VARCHAR(255) NOT NULL,"
                + "name VARCHAR(255) NOT NULL, ref_id VARCHAR(64) NOT NULL,"
                + "created_at VARCHAR(40) NOT NULL, PRIMARY KEY (id),"
                + "UNIQUE KEY uk_user_file_name (user_id, name_key),"
                + "UNIQUE KEY uk_user_file_ref (kind, ref_id),"
                + "KEY idx_user_file_user (user_id))");
        truncateAll();
        when(minio.getObject(anyString()))
                .thenReturn("正文".getBytes(StandardCharsets.UTF_8));
    }

    @AfterEach
    void clean() {
        truncateAll();
        jdbc.execute("TRUNCATE TABLE sys_user");
        jdbc.execute("TRUNCATE TABLE sys_login_log");
        jdbc.execute("TRUNCATE TABLE sys_user_role");
    }

    private void truncateAll() {
        jdbc.execute("TRUNCATE TABLE bio_user_file");
        jdbc.execute("TRUNCATE TABLE bio_paper");
        jdbc.execute("TRUNCATE TABLE bio_file_upload");
        jdbc.execute("TRUNCATE TABLE bio_document");
    }

    private String tokenFor(String userName) {
        rest.postForEntity("/api/v1/auth/register",
                Map.of("userName", userName, "password", "secret123", "nickName", userName), Map.class);
        ResponseEntity<Map> login = rest.postForEntity("/api/v1/auth/login",
                Map.of("userName", userName, "password", "secret123"), Map.class);
        return (String) ((Map) login.getBody().get("data")).get("token");
    }

    private HttpHeaders authHeaders(String token) {
        HttpHeaders headers = new HttpHeaders();
        headers.set("satoken", token);
        return headers;
    }

    private ResponseEntity<Map> upload(String token, String path, String fileName,
                                       String content, Map<String, Object> extraFields) {
        HttpHeaders headers = authHeaders(token);
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);
        MultiValueMap<String, Object> form = new LinkedMultiValueMap<>();
        form.add("file", new ByteArrayResource(content.getBytes(StandardCharsets.UTF_8)) {
            @Override
            public String getFilename() {
                return fileName;
            }
        });
        extraFields.forEach(form::add);
        return rest.exchange(path, HttpMethod.POST, new HttpEntity<>(form, headers), Map.class);
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> list(String token, String path, String key) {
        ResponseEntity<Map> response = rest.exchange(path, HttpMethod.GET,
                new HttpEntity<>(authHeaders(token)), Map.class);
        return (List<Map<String, Object>>) response.getBody().get(key);
    }

    @Test
    @Order(1)
    void paper_upload_list_duplicate_delete() {
        String token = tokenFor("catalog-user");
        ResponseEntity<Map> uploaded = upload(token, "/api/v1/papers",
                "paper.pdf", "%PDF-1.4 test", Map.of("add_to_kb", "true"));
        assertThat(uploaded.getStatusCode().value()).isEqualTo(200);
        assertThat(uploaded.getBody().get("file_name")).isEqualTo("paper.pdf");
        String paperId = (String) uploaded.getBody().get("id");
        verify(internal, org.mockito.Mockito.atLeastOnce()).kbSync(anyLong());

        List<Map<String, Object>> papers = list(token, "/api/v1/papers", "papers");
        assertThat(papers).hasSize(1);
        assertThat(papers.get(0).get("kb_enabled")).isEqualTo(1);
        assertThat(papers.get(0).get("title")).isEqualTo("");

        ResponseEntity<Map> duplicate = upload(token, "/api/v1/papers",
                "paper.pdf", "%PDF-1.4 other", Map.of());
        assertThat(duplicate.getStatusCode().value()).isEqualTo(409);

        ResponseEntity<Map> deleted = rest.exchange("/api/v1/papers/" + paperId,
                HttpMethod.DELETE, new HttpEntity<>(authHeaders(token)), Map.class);
        assertThat((String) deleted.getBody().get("status")).isEqualTo("ok");
        verify(internal, org.mockito.Mockito.atLeastOnce()).kbSync(anyLong());
        assertThat(list(token, "/api/v1/papers", "papers")).isEmpty();
    }

    @Test
    @Order(2)
    void data_file_upload_is_listed() {
        String token = tokenFor("catalog-file");
        ResponseEntity<Map> uploaded = upload(token, "/api/v1/files",
                "counts.csv", "a,b\n1,2\n", Map.of());
        assertThat(uploaded.getStatusCode().value()).isEqualTo(200);
        assertThat(uploaded.getBody().get("name")).isEqualTo("counts.csv");

        List<Map<String, Object>> files = list(token, "/api/v1/files", "files");
        assertThat(files).hasSize(1);
        assertThat(files.get(0).get("name")).isEqualTo("counts.csv");
    }

    @Test
    @Order(3)
    void document_create_read_save_delete() {
        String token = tokenFor("catalog-doc");
        HttpHeaders headers = authHeaders(token);
        headers.setContentType(MediaType.APPLICATION_JSON);
        ResponseEntity<Map> created = rest.exchange("/api/v1/documents", HttpMethod.POST,
                new HttpEntity<>(Map.of("name", "笔记.md", "content", "初始内容"), headers), Map.class);
        assertThat((String) created.getBody().get("status")).isEqualTo("ok");
        String docId = (String) created.getBody().get("id");

        ResponseEntity<Map> fetched = rest.exchange("/api/v1/documents/" + docId,
                HttpMethod.GET, new HttpEntity<>(headers), Map.class);
        assertThat(fetched.getBody().get("name")).isEqualTo("笔记.md");
        assertThat(fetched.getBody().get("content")).isEqualTo("正文");

        ResponseEntity<Map> saved = rest.exchange("/api/v1/documents/" + docId, HttpMethod.PUT,
                new HttpEntity<>(Map.of("content", "改后的内容"), headers), Map.class);
        assertThat((String) saved.getBody().get("status")).isEqualTo("ok");
        verify(minio, org.mockito.Mockito.atLeast(2))
                .putObject(anyString(), org.mockito.ArgumentMatchers.any(byte[].class), anyString());

        rest.exchange("/api/v1/documents/" + docId, HttpMethod.DELETE,
                new HttpEntity<>(headers), Map.class);
        assertThat(list(token, "/api/v1/documents", "documents")).isEmpty();
    }

    @Test
    @Order(4)
    void papers_are_isolated_per_user() {
        String owner = tokenFor("catalog-owner");
        String other = tokenFor("catalog-other");
        upload(owner, "/api/v1/papers", "owner.pdf", "%PDF-1.4 owner", Map.of());
        String paperId = (String) list(owner, "/api/v1/papers", "papers").get(0).get("id");

        assertThat(list(other, "/api/v1/papers", "papers")).isEmpty();
        ResponseEntity<Map> foreignDelete = rest.exchange("/api/v1/papers/" + paperId,
                HttpMethod.DELETE, new HttpEntity<>(authHeaders(other)), Map.class);
        assertThat(foreignDelete.getStatusCode().value()).isEqualTo(404);
        assertThat(list(owner, "/api/v1/papers", "papers")).hasSize(1);
    }

    @Test
    @Order(5)
    void kb_overview_counts_come_from_platform_table() {
        String token = tokenFor("catalog-kb");
        long uid = jdbc.queryForObject(
                "SELECT user_id FROM sys_user WHERE user_name=?", Long.class, "catalog-kb");

        Map<String, Object> runtime = new LinkedHashMap<>();
        runtime.put("collection", "biopilot_" + uid);
        runtime.put("embedding_model", "embed");
        runtime.put("running", true);
        runtime.put("last_run", Map.of("indexed", 1));
        when(internal.kbRuntime(anyLong())).thenReturn(runtime);

        insertKbPaper("k1", uid, 1, "indexed", "2026-01-02T00:00:00Z", 12);
        insertKbPaper("k2", uid, 1, "queued", null, 0);
        insertKbPaper("k3", uid, 1, "failed", null, 0);
        insertKbPaper("k4", uid, 0, "indexed", "2026-01-03T00:00:00Z", 9);

        ResponseEntity<Map> response = rest.exchange("/api/v1/kb/status", HttpMethod.GET,
                new HttpEntity<>(authHeaders(token)), Map.class);
        assertThat(response.getStatusCode().value()).isEqualTo(200);
        Map body = response.getBody();
        assertThat(body.get("total_papers")).isEqualTo(4);
        assertThat(body.get("kb_enabled")).isEqualTo(3);
        assertThat(body.get("indexed")).isEqualTo(1);
        assertThat(body.get("queued")).isEqualTo(1);
        assertThat(body.get("failed")).isEqualTo(1);
        assertThat(body.get("not_added")).isEqualTo(1);
        // 未勾选行即使残留 chunk_count/indexed 也不计入统计
        assertThat(body.get("chunks")).isEqualTo(12);
        assertThat(body.get("last_indexed_at")).isEqualTo("2026-01-02T00:00:00Z");
        assertThat(body.get("collection")).isEqualTo("biopilot_" + uid);
        assertThat(body.get("embedding_model")).isEqualTo("embed");
        assertThat(body.get("running")).isEqualTo(true);

        String other = tokenFor("catalog-kb-other");
        ResponseEntity<Map> isolated = rest.exchange("/api/v1/kb/status", HttpMethod.GET,
                new HttpEntity<>(authHeaders(other)), Map.class);
        assertThat(isolated.getBody().get("total_papers")).isEqualTo(0);
        assertThat(isolated.getBody().get("kb_enabled")).isEqualTo(0);
    }

    private void insertKbPaper(String id, long userId, int kb, String status,
                               String indexedAt, int chunks) {
        jdbc.update("INSERT INTO bio_paper (id, user_id, title, file_name, oss_key,"
                        + " size_bytes, indexed, kb_enabled, index_status, indexed_at,"
                        + " chunk_count, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                id, String.valueOf(userId), "t", id + ".pdf",
                "users/" + userId + "/papers/" + id + "/a.pdf", 10,
                "indexed".equals(status) ? 1 : 0, kb, status, indexedAt, chunks,
                "2026-01-01T00:00:00Z");
    }
}
