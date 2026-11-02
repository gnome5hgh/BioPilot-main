package com.biopilot.file.service.impl;

import com.biopilot.file.service.DocumentService;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.biopilot.file.domain.BioDocument;
import com.biopilot.file.dto.DocumentSummary;
import com.biopilot.file.dto.DocumentView;
import com.biopilot.file.mapper.BioDocumentMapper;
import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.common.oss.core.MinioTemplate;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import com.biopilot.file.service.FileCatalogService;

/** 文档编辑器：bio_document 元数据 + OSS 正文。 */
@Service
public class DocumentServiceImpl implements DocumentService {

    private final BioDocumentMapper documentMapper;
    private final FileCatalogService catalog;
    private final MinioTemplate minio;

    public DocumentServiceImpl(BioDocumentMapper documentMapper, FileCatalogService catalog,
                           MinioTemplate minio) {
        this.documentMapper = documentMapper;
        this.catalog = catalog;
        this.minio = minio;
    }

    public List<DocumentSummary> list(long userId) {
        return documentMapper.selectList(new QueryWrapper<BioDocument>().orderByDesc("seq"))
                .stream()
                .map(d -> new DocumentSummary(d.getId(), d.getName(), d.getUpdatedAt()))
                .toList();
    }

    public Map<String, Object> create(long userId, Map<String, Object> body) {
        String name = String.valueOf(body.getOrDefault("name", "新文档.md")).trim();
        if (name.isEmpty()) {
            name = "新文档.md";
        }
        catalog.assertNameAvailable(name);
        String content = String.valueOf(body.getOrDefault("content", ""));
        String id = UUID.randomUUID().toString().replace("-", "");
        String ossKey = ossKey(userId, name);
        minio.putObject(ossKey, content.getBytes(StandardCharsets.UTF_8), "text/markdown");
        BioDocument doc = new BioDocument();
        doc.setId(id);
        doc.setUserId(String.valueOf(userId));
        doc.setName(name);
        doc.setContent(content);
        doc.setOssKey(ossKey);
        doc.setUpdatedAt(now());
        documentMapper.insert(doc);
        return Map.of("status", "ok", "id", id);
    }

    public DocumentView get(long userId, String docId) {
        BioDocument doc = find(docId);
        String content = doc.getContent();
        if (doc.getOssKey() != null && !doc.getOssKey().isBlank()) {
            try {
                content = new String(minio.getObject(doc.getOssKey()), StandardCharsets.UTF_8);
            } catch (RuntimeException ignored) {
                // OSS 不可达时回退行内 content（遗留行兜底）
            }
        }
        return new DocumentView(doc.getId(), doc.getName(), content, doc.getUpdatedAt());
    }

    public Map<String, Object> save(long userId, String docId, Map<String, Object> body) {
        BioDocument doc = find(docId);
        String content = String.valueOf(body.getOrDefault("content", ""));
        String name = body.get("name") == null ? null : String.valueOf(body.get("name")).trim();
        if (name != null && !name.isEmpty() && !name.equals(doc.getName())) {
            catalog.assertNameAvailable(name, "document", docId);
        }
        String ossKey = doc.getOssKey();
        if (ossKey == null || ossKey.isBlank()) {
            ossKey = ossKey(userId, name == null || name.isEmpty() ? doc.getName() : name);
        }
        minio.putObject(ossKey, content.getBytes(StandardCharsets.UTF_8), "text/markdown");
        doc.setContent(content);
        doc.setOssKey(ossKey);
        if (name != null && !name.isEmpty()) {
            doc.setName(name);
        }
        doc.setUpdatedAt(now());
        documentMapper.updateById(doc);
        return Map.of("status", "ok");
    }

    /**
     * agent 成稿入库：按 (user_id, name) upsert，内容先落 OSS、后写行。
     *
     * <p>引擎内部调用没有浏览器登录态，故走显式 user_id 的 mapper 方法；同名覆盖
     * 语义与 Python 旧工具一致，不做跨类型同名检查（旧行为也不做）。</p>
     *
     * @param userId  归属用户（字符串，兼容 REPL 的 local 域）
     * @param rawName 文档名（超 200 字符截断，非法路径字符替换为下划线）
     * @param content markdown 全文
     * @return {@code {status, id, name, created}}
     */
    public Map<String, Object> saveByName(String userId, String rawName, String content) {
        String name = safeDocumentName(rawName);
        String ossKey = "users/" + userId + "/files/documents/" + name;
        minio.putObject(ossKey, content.getBytes(StandardCharsets.UTF_8), "text/markdown");
        BioDocument existing = documentMapper.selectByUserAndNameForAgent(userId, name);
        if (existing != null) {
            documentMapper.updateForAgent(existing.getId(), userId, content, ossKey, now());
            return Map.of("status", "ok", "id", existing.getId(),
                    "name", name, "created", false);
        }
        String id = UUID.randomUUID().toString().replace("-", "");
        documentMapper.insertForAgent(id, userId, name, content, ossKey, now());
        return Map.of("status", "ok", "id", id, "name", name, "created", true);
    }

    private static String safeDocumentName(String rawName) {
        String name = rawName == null ? "" : rawName.trim();
        if (name.isEmpty()) {
            throw new ServiceException(422, "文档名不能为空");
        }
        if (name.length() > 200) {
            name = name.substring(0, 200);
        }
        String safe = name.replaceAll("[\\\\/:*?\"<>|\\x00-\\x1f]", "_").trim();
        return safe.isEmpty() ? "未命名.md" : safe;
    }

    public void delete(long userId, String docId) {
        BioDocument doc = find(docId);
        documentMapper.deleteById(docId);
        if (doc.getOssKey() != null && !doc.getOssKey().isBlank()) {
            try {
                minio.removeObject(doc.getOssKey());
            } catch (RuntimeException ignored) {
                // 行已删；对象删除失败只留孤儿
            }
        }
    }

    private BioDocument find(String docId) {
        BioDocument doc = documentMapper.selectOne(new LambdaQueryWrapper<BioDocument>()
                .eq(BioDocument::getId, docId));
        if (doc == null) {
            throw new ServiceException(404, "文档不存在");
        }
        return doc;
    }

    private String ossKey(long userId, String name) {
        return "users/" + userId + "/files/documents/" + name;
    }

    private String now() {
        return OffsetDateTime.now(ZoneOffset.UTC).toString();
    }
}
