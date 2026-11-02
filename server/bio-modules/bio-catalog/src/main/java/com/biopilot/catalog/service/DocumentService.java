package com.biopilot.catalog.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.biopilot.catalog.domain.BioDocument;
import com.biopilot.catalog.dto.DocumentSummary;
import com.biopilot.catalog.dto.DocumentView;
import com.biopilot.catalog.mapper.BioDocumentMapper;
import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.common.oss.core.MinioTemplate;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;

/** 文档编辑器：bio_document 元数据 + OSS 正文。 */
@Service
public class DocumentService {

    private final BioDocumentMapper documentMapper;
    private final FileCatalogService catalog;
    private final MinioTemplate minio;

    public DocumentService(BioDocumentMapper documentMapper, FileCatalogService catalog,
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
