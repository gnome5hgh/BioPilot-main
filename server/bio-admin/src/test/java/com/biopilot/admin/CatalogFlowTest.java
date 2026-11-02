package com.biopilot.admin;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.verify;
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
                "spring.datasource.url=jdbc:mysql://127.0.0.1:3306/biopilot_test"
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
        jdbc.execute("CREATE TABLE IF NOT EXISTS bio_paper ("
                + "id VARCHAR(64) NOT NULL, user_id VARCHAR(191) NOT NULL,"
                + "title VARCHAR(500) NOT NULL, file_name VARCHAR(255) NULL,"
                + "oss_key VARCHAR(500) NOT NULL, size_bytes BIGINT NOT NULL DEFAULT 0,"
                + "indexed INTEGER NOT NULL DEFAULT 0, kb_enabled TINYINT NOT NULL DEFAULT 0,"
                + "index_status VARCHAR(20) NOT NULL DEFAULT 'not_added',"
                + "index_error VARCHAR(500) NULL, indexed_at VARCHAR(40) NULL,"
                + "chunk_count INT NOT NULL DEFAULT 0, created_at VARCHAR(40) NOT NULL,"
                + "seq BIGINT NOT NULL AUTO_INCREMENT, PRIMARY KEY (id),"
                + "UNIQUE KEY uk_papers_seq (seq), KEY idx_papers_user (user_id))");
        jdbc.execute("CREATE TABLE IF NOT EXISTS bio_file_upload ("
                + "id VARCHAR(64) NOT NULL, user_id VARCHAR(191) NOT NULL,"
                + "name VARCHAR(255) NOT NULL, oss_key VARCHAR(500) NOT NULL,"
                + "size_bytes BIGINT NOT NULL DEFAULT 0, content_type VARCHAR(120) NULL,"
                + "created_at VARCHAR(40) NOT NULL, PRIMARY KEY (id),"
                + "KEY idx_upload_user (user_id))");
        jdbc.execute("CREATE TABLE IF NOT EXISTS bio_document ("
                + "id VARCHAR(64) NOT NULL, user_id VARCHAR(191) NOT NULL,"
                + "name VARCHAR(200) NOT NULL, content MEDIUMTEXT NULL,"
                + "oss_key VARCHAR(500) NULL, updated_at VARCHAR(40) NOT NULL,"
                + "seq BIGINT NOT NULL AUTO_INCREMENT, PRIMARY KEY (id),"
                + "UNIQUE KEY uk_documents_seq (seq), KEY idx_documents_user (user_id))");
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
        jdbc.execute("TRUNCATE TABLE bio_paper");
        jdbc.execute("TRUNCATE TABLE bio_file_upload");
        jdbc.execute("TRUNCATE TABLE bio_document");
    }

    private String tokenFor(String userName) {
        rest.postForEntity("/auth/register",
                Map.of("userName", userName, "password", "secret123", "nickName", userName), Map.class);
        ResponseEntity<Map> login = rest.postForEntity("/auth/login",
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
        ResponseEntity<Map> uploaded = upload(token, "/agent/papers/upload",
                "paper.pdf", "%PDF-1.4 test", Map.of("add_to_kb", "true"));
        assertThat(uploaded.getStatusCode().value()).isEqualTo(200);
        assertThat(uploaded.getBody().get("file_name")).isEqualTo("paper.pdf");
        String paperId = (String) uploaded.getBody().get("id");
        verify(internal).kbEnqueue(anyLong(), org.mockito.ArgumentMatchers.anyList());

        List<Map<String, Object>> papers = list(token, "/agent/papers", "papers");
        assertThat(papers).hasSize(1);
        assertThat(papers.get(0).get("kb_enabled")).isEqualTo(1);
        assertThat(papers.get(0).get("title")).isEqualTo("");

        ResponseEntity<Map> duplicate = upload(token, "/agent/papers/upload",
                "paper.pdf", "%PDF-1.4 other", Map.of());
        assertThat(duplicate.getStatusCode().value()).isEqualTo(409);

        ResponseEntity<Map> deleted = rest.exchange("/agent/papers/" + paperId,
                HttpMethod.DELETE, new HttpEntity<>(authHeaders(token)), Map.class);
        assertThat((String) deleted.getBody().get("status")).isEqualTo("ok");
        verify(internal).kbSync(anyLong());
        assertThat(list(token, "/agent/papers", "papers")).isEmpty();
    }

    @Test
    @Order(2)
    void data_file_upload_is_listed() {
        String token = tokenFor("catalog-file");
        ResponseEntity<Map> uploaded = upload(token, "/agent/files/upload",
                "counts.csv", "a,b\n1,2\n", Map.of());
        assertThat(uploaded.getStatusCode().value()).isEqualTo(200);
        assertThat(uploaded.getBody().get("name")).isEqualTo("counts.csv");

        List<Map<String, Object>> files = list(token, "/agent/files", "files");
        assertThat(files).hasSize(1);
        assertThat(files.get(0).get("name")).isEqualTo("counts.csv");
    }

    @Test
    @Order(3)
    void document_create_read_save_delete() {
        String token = tokenFor("catalog-doc");
        HttpHeaders headers = authHeaders(token);
        headers.setContentType(MediaType.APPLICATION_JSON);
        ResponseEntity<Map> created = rest.exchange("/agent/documents", HttpMethod.POST,
                new HttpEntity<>(Map.of("name", "笔记.md", "content", "初始内容"), headers), Map.class);
        assertThat((String) created.getBody().get("status")).isEqualTo("ok");
        String docId = (String) created.getBody().get("id");

        ResponseEntity<Map> fetched = rest.exchange("/agent/documents/" + docId,
                HttpMethod.GET, new HttpEntity<>(headers), Map.class);
        assertThat(fetched.getBody().get("name")).isEqualTo("笔记.md");
        assertThat(fetched.getBody().get("content")).isEqualTo("正文");

        ResponseEntity<Map> saved = rest.exchange("/agent/documents/" + docId, HttpMethod.PUT,
                new HttpEntity<>(Map.of("content", "改后的内容"), headers), Map.class);
        assertThat((String) saved.getBody().get("status")).isEqualTo("ok");
        verify(minio, org.mockito.Mockito.atLeast(2))
                .putObject(anyString(), org.mockito.ArgumentMatchers.any(byte[].class), anyString());

        rest.exchange("/agent/documents/" + docId, HttpMethod.DELETE,
                new HttpEntity<>(headers), Map.class);
        assertThat(list(token, "/agent/documents", "documents")).isEmpty();
    }

    @Test
    @Order(4)
    void papers_are_isolated_per_user() {
        String owner = tokenFor("catalog-owner");
        String other = tokenFor("catalog-other");
        upload(owner, "/agent/papers/upload", "owner.pdf", "%PDF-1.4 owner", Map.of());
        String paperId = (String) list(owner, "/agent/papers", "papers").get(0).get("id");

        assertThat(list(other, "/agent/papers", "papers")).isEmpty();
        ResponseEntity<Map> foreignDelete = rest.exchange("/agent/papers/" + paperId,
                HttpMethod.DELETE, new HttpEntity<>(authHeaders(other)), Map.class);
        assertThat(foreignDelete.getStatusCode().value()).isEqualTo(404);
        assertThat(list(owner, "/agent/papers", "papers")).hasSize(1);
    }
}
