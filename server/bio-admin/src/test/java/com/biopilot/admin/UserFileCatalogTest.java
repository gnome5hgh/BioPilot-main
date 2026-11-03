package com.biopilot.admin;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.clearInvocations;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.biopilot.common.oss.core.MinioTemplate;
import com.biopilot.common.web.http.AgentInternalClient;
import com.biopilot.file.service.impl.UserFileCatalogBackfillRunner;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
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
 * 用户文件同名约束：数据库唯一键裁决、并发、跨类型、释放、改名与存量回填。
 *
 * <p>并发用例走真实 HTTP（两个独立请求线程），验证的是「数据库唯一键」而不是
 * 应用层先查后插；OSS 与引擎调用打桩。</p>
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "spring.datasource.url=jdbc:mysql://127.0.0.1:3307/biopilot_test"
                        + "?useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Shanghai",
        })
class UserFileCatalogTest {

    @Autowired
    TestRestTemplate rest;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    UserFileCatalogBackfillRunner backfillRunner;

    @MockBean
    MinioTemplate minio;

    @MockBean
    AgentInternalClient internal;

    @BeforeEach
    void setUp() {
        dropAndCreateTables();
        when(minio.getObject(anyString()))
                .thenReturn("正文".getBytes(StandardCharsets.UTF_8));
    }

    @AfterEach
    void clean() {
        jdbc.execute("TRUNCATE TABLE sys_user");
        jdbc.execute("TRUNCATE TABLE sys_login_log");
        jdbc.execute("TRUNCATE TABLE sys_user_role");
    }

    @Test
    void concurrent_same_name_upload_has_single_winner() throws Exception {
        String token = tokenFor("catalog-race");
        clearInvocations(minio);

        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> first = pool.submit(() -> {
                start.await();
                return uploadStatus(token, "/api/v1/papers", "race.pdf", "%PDF-1.4 a");
            });
            Future<Integer> second = pool.submit(() -> {
                start.await();
                return uploadStatus(token, "/api/v1/papers", "race.pdf", "%PDF-1.4 b");
            });
            start.countDown();
            List<Integer> statuses = List.of(first.get(30, TimeUnit.SECONDS),
                    second.get(30, TimeUnit.SECONDS));

            assertThat(statuses).containsExactlyInAnyOrder(200, 409);
            assertThat(count("bio_paper")).isEqualTo(1);
            assertThat(count("bio_user_file")).isEqualTo(1);
            // 落败者也写过对象，冲突后必须补偿删除，不能留孤儿
            verify(minio, times(1)).removeObject(anyString());
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void same_name_is_shared_across_file_types() {
        String token = tokenFor("catalog-cross-type");
        assertThat(uploadStatus(token, "/api/v1/papers", "shared.md", "%PDF-1.4")).isEqualTo(200);

        ResponseEntity<Map> created = createDocument(token, "shared.md", "x");
        assertThat(created.getStatusCode().value()).isEqualTo(409);
        assertThat(count("bio_user_file")).isEqualTo(1);
    }

    @Test
    void delete_releases_the_name() {
        String token = tokenFor("catalog-release");
        assertThat(uploadStatus(token, "/api/v1/papers", "again.pdf", "%PDF-1.4")).isEqualTo(200);
        String paperId = jdbc.queryForObject(
                "SELECT id FROM bio_paper WHERE file_name='again.pdf'", String.class);

        rest.exchange("/api/v1/papers/" + paperId, HttpMethod.DELETE,
                new HttpEntity<>(authHeaders(token)), Map.class);

        assertThat(count("bio_user_file")).isZero();
        assertThat(uploadStatus(token, "/api/v1/papers", "again.pdf", "%PDF-1.4")).isEqualTo(200);
    }

    @Test
    void different_users_may_use_the_same_name() {
        String owner = tokenFor("catalog-name-a");
        String other = tokenFor("catalog-name-b");

        assertThat(uploadStatus(owner, "/api/v1/papers", "same.pdf", "%PDF-1.4")).isEqualTo(200);
        assertThat(uploadStatus(other, "/api/v1/papers", "same.pdf", "%PDF-1.4")).isEqualTo(200);
        assertThat(count("bio_user_file")).isEqualTo(2);
    }

    @Test
    void case_and_surrounding_spaces_collide() {
        String token = tokenFor("catalog-case");
        assertThat(uploadStatus(token, "/api/v1/papers", "Paper.PDF", "%PDF-1.4")).isEqualTo(200);
        assertThat(uploadStatus(token, "/api/v1/papers", "  paper.pdf ", "%PDF-1.4"))
                .isEqualTo(409);
    }

    @Test
    void document_rename_collision_returns_409_and_success_moves_name() {
        String token = tokenFor("catalog-rename");
        createDocument(token, "a.md", "a");
        String bId = (String) createDocument(token, "b.md", "b").getBody().get("id");

        HttpHeaders headers = authHeaders(token);
        headers.setContentType(MediaType.APPLICATION_JSON);
        ResponseEntity<Map> conflict = rest.exchange("/api/v1/documents/" + bId,
                HttpMethod.PUT, new HttpEntity<>(Map.of("name", "a.md", "content", "b2"), headers),
                Map.class);
        assertThat(conflict.getStatusCode().value()).isEqualTo(409);

        ResponseEntity<Map> ok = rest.exchange("/api/v1/documents/" + bId,
                HttpMethod.PUT, new HttpEntity<>(Map.of("name", "c.md", "content", "b2"), headers),
                Map.class);
        assertThat(ok.getStatusCode().value()).isEqualTo(200);
        ResponseEntity<Map> fetched = rest.exchange("/api/v1/documents/" + bId,
                HttpMethod.GET, new HttpEntity<>(headers), Map.class);
        assertThat(fetched.getBody().get("name")).isEqualTo("c.md");
    }

    @Test
    void save_by_name_upserts_and_blocks_cross_type() {
        String token = tokenFor("catalog-agent-save");
        long uid = jdbc.queryForObject(
                "SELECT user_id FROM sys_user WHERE user_name=?", Long.class, "catalog-agent-save");
        String user = String.valueOf(uid);

        // 同名论文存在时，agent 成稿不能覆盖它
        assertThat(uploadStatus(token, "/api/v1/papers", "conflict.md", "%PDF-1.4"))
                .isEqualTo(200);
        ResponseEntity<Map> blocked = internalSave(user,
                Map.of("name", "conflict.md", "content", "不能覆盖论文"));
        assertThat(blocked.getStatusCode().value()).isEqualTo(409);
        assertThat(count("bio_document")).isZero();

        // 文档自身按名字 upsert：第二次更新同一条
        assertThat(internalSave(user, Map.of("name", "agent-note.md", "content", "第一版"))
                .getBody().get("created")).isEqualTo(true);
        assertThat(internalSave(user, Map.of("name", "agent-note.md", "content", "第二版"))
                .getBody().get("created")).isEqualTo(false);
        assertThat(count("bio_document")).isEqualTo(1);
        assertThat(countWhere("bio_user_file", "kind='document'")).isEqualTo(1);
    }

    @Test
    void accent_and_case_folding_are_not_collapsed_by_db_collation() {
        String token = tokenFor("catalog-accent");
        assertThat(createDocument(token, "café.md", "1").getStatusCode().value()).isEqualTo(200);
        // name_key 用二进制排序规则：cafe.md 与 café.md 是两个名字
        assertThat(createDocument(token, "cafe.md", "2").getStatusCode().value()).isEqualTo(200);
        assertThat(countWhere("bio_user_file", "kind='document'")).isEqualTo(2);
    }

    @Test
    void internal_save_releases_dangling_registry_row_without_login() {
        // 模拟「登记行在、文档行已删」：内部路径必须先释放再回 409，且不能 500
        jdbc.update("INSERT INTO bio_user_file"
                        + " (user_id, kind, name_key, name, ref_id, created_at)"
                        + " VALUES ('4242','document','ghost.md','ghost.md','missing-doc',"
                        + "'2026-01-01T00:00:00+00:00')");

        ResponseEntity<Map> response = internalSave("4242",
                Map.of("name", "ghost.md", "content", "x"));

        assertThat(response.getStatusCode().value()).isEqualTo(409);
        assertThat(countWhere("bio_user_file", "ref_id='missing-doc'")).isZero();
    }

    @Test
    void backfill_registers_existing_rows_and_renames_duplicates() {
        jdbc.update("INSERT INTO bio_paper (id, user_id, title, file_name, oss_key, created_at)"
                + " VALUES ('bp1','42','t1','dup.pdf','users/42/papers/bp1/dup.pdf',"
                + "'2026-01-01T00:00:00+00:00')");
        jdbc.update("INSERT INTO bio_paper (id, user_id, title, file_name, oss_key, created_at)"
                + " VALUES ('bp2','42','t2','dup.pdf','users/42/papers/bp2/dup.pdf',"
                + "'2026-01-02T00:00:00+00:00')");
        // 展示名缺失：按列表页口径取 OSS 键末段登记，不能漏进无约束状态
        jdbc.update("INSERT INTO bio_paper (id, user_id, title, file_name, oss_key, created_at)"
                + " VALUES ('bp3','42','t3',NULL,'users/42/papers/bp3/fallback.pdf',"
                + "'2026-01-03T00:00:00+00:00')");
        // 分析产物不参与同名登记
        jdbc.update("INSERT INTO bio_file_upload (id, user_id, name, oss_key, source, created_at)"
                + " VALUES ('f1','42','volcano.png','users/42/files/analysis/r1/volcano.png',"
                + "'artifact','2026-01-04T00:00:00+00:00')");
        // 文档列宽 200：替名不能越过列宽（否则整轮回填被异常打断）
        String longName = "x".repeat(196) + ".md";     // 199 字符
        jdbc.update("INSERT INTO bio_document (id, user_id, name, content, oss_key, updated_at)"
                + " VALUES ('d1','42',?, 'a','users/42/files/documents/d1.md',"
                + "'2026-01-05T00:00:00+00:00')", longName);
        jdbc.update("INSERT INTO bio_document (id, user_id, name, content, oss_key, updated_at)"
                + " VALUES ('d2','42',?, 'b','users/42/files/documents/d2.md',"
                + "'2026-01-06T00:00:00+00:00')", longName);

        backfillRunner.run(null);

        assertThat(countWhere("bio_user_file", "kind='paper'")).isEqualTo(3);
        assertThat(countWhere("bio_user_file", "kind='file'")).isZero();
        assertThat(countWhere("bio_user_file",
                "ref_id='bp3' AND name_key='fallback.pdf'")).isEqualTo(1);
        String renamed = jdbc.queryForObject(
                "SELECT file_name FROM bio_paper WHERE id='bp2'", String.class);
        assertThat(renamed).isEqualTo("dup (2).pdf");

        List<String> docNames = jdbc.queryForList(
                "SELECT name FROM bio_document ORDER BY id", String.class);
        assertThat(docNames).hasSize(2).doesNotHaveDuplicates();
        assertThat(docNames).allMatch(name -> name.length() <= 200);
    }

    // ---- helpers ----

    private int count(String table) {
        Integer value = jdbc.queryForObject("SELECT COUNT(*) FROM " + table, Integer.class);
        return value == null ? 0 : value;
    }

    private int countWhere(String table, String where) {
        Integer value = jdbc.queryForObject(
                "SELECT COUNT(*) FROM " + table + " WHERE " + where, Integer.class);
        return value == null ? 0 : value;
    }

    private String tokenFor(String userName) {
        rest.postForEntity("/api/v1/auth/register",
                Map.of("userName", userName, "password", "secret123", "nickName", userName),
                Map.class);
        ResponseEntity<Map> login = rest.postForEntity("/api/v1/auth/login",
                Map.of("userName", userName, "password", "secret123"), Map.class);
        return (String) ((Map) login.getBody().get("data")).get("token");
    }

    private HttpHeaders authHeaders(String token) {
        HttpHeaders headers = new HttpHeaders();
        headers.set("satoken", token);
        return headers;
    }

    private int uploadStatus(String token, String path, String fileName, String content) {
        HttpHeaders headers = authHeaders(token);
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);
        MultiValueMap<String, Object> form = new LinkedMultiValueMap<>();
        form.add("file", new ByteArrayResource(content.getBytes(StandardCharsets.UTF_8)) {
            @Override
            public String getFilename() {
                return fileName;
            }
        });
        return rest.exchange(path, HttpMethod.POST, new HttpEntity<>(form, headers), Map.class)
                .getStatusCode().value();
    }

    private ResponseEntity<Map> createDocument(String token, String name, String content) {
        HttpHeaders headers = authHeaders(token);
        headers.setContentType(MediaType.APPLICATION_JSON);
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("name", name);
        body.put("content", content);
        return rest.exchange("/api/v1/documents", HttpMethod.POST,
                new HttpEntity<>(body, headers), Map.class);
    }

    private ResponseEntity<Map> internalSave(String userId, Map<String, Object> body) {
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-User-Id", userId);
        headers.setContentType(MediaType.APPLICATION_JSON);
        return rest.exchange("/internal/documents/save", HttpMethod.POST,
                new HttpEntity<>(body, headers), Map.class);
    }

    private void dropAndCreateTables() {
        for (String table : List.of("bio_paper", "bio_file_upload", "bio_document",
                "bio_user_file")) {
            jdbc.execute("DROP TABLE IF EXISTS " + table);
        }
        jdbc.execute("CREATE TABLE bio_paper ("
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
        jdbc.execute("CREATE TABLE bio_file_upload ("
                + "id VARCHAR(64) NOT NULL, user_id VARCHAR(191) NOT NULL,"
                + "name VARCHAR(255) NOT NULL, oss_key VARCHAR(500) NOT NULL,"
                + "size_bytes BIGINT NOT NULL DEFAULT 0, content_type VARCHAR(120) NULL,"
                + "source VARCHAR(16) NOT NULL DEFAULT 'upload',"
                + "created_at VARCHAR(40) NOT NULL, PRIMARY KEY (id),"
                + "KEY idx_upload_user (user_id))");
        jdbc.execute("CREATE TABLE bio_document ("
                + "id VARCHAR(64) NOT NULL, user_id VARCHAR(191) NOT NULL,"
                + "name VARCHAR(200) NOT NULL, content MEDIUMTEXT NULL,"
                + "oss_key VARCHAR(500) NULL, updated_at VARCHAR(40) NOT NULL,"
                + "seq BIGINT NOT NULL AUTO_INCREMENT, PRIMARY KEY (id),"
                + "UNIQUE KEY uk_documents_seq (seq), KEY idx_documents_user (user_id))");
        jdbc.execute("CREATE TABLE bio_user_file ("
                + "id BIGINT NOT NULL AUTO_INCREMENT, user_id VARCHAR(191) NOT NULL,"
                + "kind VARCHAR(16) NOT NULL, name_key VARCHAR(255) COLLATE utf8mb4_0900_bin NOT NULL,"
                + "name VARCHAR(255) NOT NULL, ref_id VARCHAR(64) NOT NULL,"
                + "created_at VARCHAR(40) NOT NULL, PRIMARY KEY (id),"
                + "UNIQUE KEY uk_user_file_name (user_id, name_key),"
                + "UNIQUE KEY uk_user_file_ref (kind, ref_id),"
                + "KEY idx_user_file_user (user_id))");
    }
}
