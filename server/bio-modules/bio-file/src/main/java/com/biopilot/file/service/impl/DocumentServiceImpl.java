package com.biopilot.file.service.impl;

import com.biopilot.file.service.DocumentService;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.biopilot.file.domain.BioDocument;
import com.biopilot.file.domain.FileObjectKeys;
import com.biopilot.file.domain.UserFileKind;
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
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import com.biopilot.file.service.FileCatalogService;

/** 文档编辑器：bio_document 元数据 + OSS 正文。 */
@Service
public class DocumentServiceImpl implements DocumentService {

    private final BioDocumentMapper documentMapper;
    private final FileCatalogService catalog;
    private final MinioTemplate minio;
    private final TransactionTemplate transaction;

    public DocumentServiceImpl(BioDocumentMapper documentMapper, FileCatalogService catalog,
                           MinioTemplate minio,
                           PlatformTransactionManager transactionManager) {
        this.documentMapper = documentMapper;
        this.catalog = catalog;
        this.minio = minio;
        this.transaction = new TransactionTemplate(transactionManager);
    }

    public List<DocumentSummary> list(long userId) {
        return documentMapper.selectList(new QueryWrapper<BioDocument>().orderByDesc("seq"))
                .stream()
                .map(d -> new DocumentSummary(d.getId(), d.getName(), d.getUpdatedAt()))
                .toList();
    }

    public Map<String, Object> create(long userId, Map<String, Object> body) {
        String rawName = String.valueOf(body.getOrDefault("name", "新文档.md")).trim();
        String name = rawName.isEmpty() ? "新文档.md" : rawName;
        String content = String.valueOf(body.getOrDefault("content", ""));
        String user = String.valueOf(userId);
        String id = UUID.randomUUID().toString().replace("-", "");
        String ossKey = FileObjectKeys.document(user, id);
        minio.putObject(ossKey, content.getBytes(StandardCharsets.UTF_8), "text/markdown");
        BioDocument doc = new BioDocument();
        doc.setId(id);
        doc.setUserId(user);
        doc.setName(name);
        doc.setContent(content);
        doc.setOssKey(ossKey);
        doc.setUpdatedAt(now());
        try {
            transaction.executeWithoutResult(status -> {
                catalog.reserve(user, UserFileKind.DOCUMENT.code(), name, id);
                documentMapper.insert(doc);
            });
        } catch (RuntimeException e) {
            quietRemove(ossKey);
            throw e;
        }
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
        String finalName = name == null || name.isEmpty() ? doc.getName() : name;
        boolean renamed = !finalName.equals(doc.getName());
        String user = String.valueOf(userId);
        if (renamed) {
            // 预检让常见冲突在写对象前返回 409；并发窗口仍由唯一键兜底
            catalog.assertNameAvailable(finalName, UserFileKind.DOCUMENT.code(), docId);
        }
        String oldKey = doc.getOssKey();
        String ossKey = FileObjectKeys.document(user, docId);
        // 对象先落、行后写：文档键按 id 生成，改名不再搬对象，
        // 也避免「A 改名 B 后新建 A」写进同一个对象覆盖正文。
        minio.putObject(ossKey, content.getBytes(StandardCharsets.UTF_8), "text/markdown");
        doc.setContent(content);
        doc.setOssKey(ossKey);
        doc.setName(finalName);
        doc.setUpdatedAt(now());
        try {
            transaction.executeWithoutResult(status -> {
                if (renamed) {
                    catalog.rename(user, UserFileKind.DOCUMENT.code(), docId, finalName);
                }
                documentMapper.updateById(doc);
            });
        } catch (RuntimeException e) {
            if (!ossKey.equals(oldKey)) {
                // 新键是本次懒迁移写出的；同键覆盖无法回滚，行内 content 仍可兜底
                quietRemove(ossKey);
            }
            throw e;
        }
        removeLegacyKey(user, oldKey, ossKey);
        return Map.of("status", "ok");
    }

    /**
     * agent 成稿入库：按 (user_id, 归一化名) upsert，内容先落 OSS、后写行。
     *
     * <p>引擎内部调用没有浏览器登录态，名字登记走显式 user_id 的查询与占名。
     * 同名目标若是论文/数据文件，返回冲突而不是覆盖。</p>
     *
     * @param userId  归属用户（字符串，兼容 REPL 的 local 域）
     * @param rawName 文档名（超 200 字符截断，非法路径字符替换为下划线）
     * @param content markdown 全文
     * @return {@code {status, id, name, created}}
     */
    public Map<String, Object> saveByName(String userId, String rawName, String content) {
        String name = safeDocumentName(rawName);
        String user = String.valueOf(userId);
        FileCatalogService.Reservation existing = catalog.find(user, name);
        if (existing != null && !UserFileKind.DOCUMENT.code().equals(existing.kind())) {
            throw FileCatalogService.conflict(name, existing.kind());
        }
        if (existing != null) {
            return updateExisting(user, existing.refId(), name, content);
        }
        String id = UUID.randomUUID().toString().replace("-", "");
        String ossKey = FileObjectKeys.document(user, id);
        minio.putObject(ossKey, content.getBytes(StandardCharsets.UTF_8), "text/markdown");
        try {
            transaction.executeWithoutResult(status -> {
                catalog.reserve(user, UserFileKind.DOCUMENT.code(), name, id);
                documentMapper.insertForAgent(id, user, name, content, ossKey, now());
            });
            return Map.of("status", "ok", "id", id, "name", name, "created", true);
        } catch (RuntimeException e) {
            quietRemove(ossKey);
            // 并发抢名：对手若也是文档就改成更新，否则如实回冲突
            FileCatalogService.Reservation winner = catalog.find(user, name);
            if (winner != null && UserFileKind.DOCUMENT.code().equals(winner.kind())) {
                return updateExisting(user, winner.refId(), name, content);
            }
            if (winner != null) {
                throw FileCatalogService.conflict(name, winner.kind());
            }
            throw e;
        }
    }

    public void delete(long userId, String docId) {
        BioDocument doc = find(docId);
        transaction.executeWithoutResult(status -> {
            catalog.release(UserFileKind.DOCUMENT.code(), docId);
            documentMapper.deleteById(docId);
        });
        if (doc.getOssKey() != null && !doc.getOssKey().isBlank()) {
            quietRemove(doc.getOssKey());
        }
    }

    /** 更新已有文档的正文；对象键按 id 生成，旧的名字基键在成功后清理。 */
    private Map<String, Object> updateExisting(String user, String docId, String name,
                                               String content) {
        BioDocument existing = documentMapper.selectByIdForAgent(user, docId);
        if (existing == null) {
            // 登记行指向的文档已不存在：清掉悬空登记，让本次调用按新建重来
            catalog.release(UserFileKind.DOCUMENT.code(), docId);
            throw new ServiceException(409, "文档登记已失效，请重试");
        }
        String ossKey = FileObjectKeys.document(user, docId);
        minio.putObject(ossKey, content.getBytes(StandardCharsets.UTF_8), "text/markdown");
        transaction.executeWithoutResult(status ->
                documentMapper.updateForAgent(docId, user, content, ossKey, now()));
        removeLegacyKey(user, existing.getOssKey(), ossKey);
        return Map.of("status", "ok", "id", docId, "name", name, "created", false);
    }

    private BioDocument find(String docId) {
        BioDocument doc = documentMapper.selectOne(new LambdaQueryWrapper<BioDocument>()
                .eq(BioDocument::getId, docId));
        if (doc == null) {
            throw new ServiceException(404, "文档不存在");
        }
        return doc;
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

    /**
     * 清理旧的名字基对象键：它可能仍被同名的另一行共用（并发重复的历史数据），
     * 只有确认没有其他行引用时才删除，否则留给后台对账。
     */
    private void removeLegacyKey(String user, String oldKey, String newKey) {
        if (oldKey == null || oldKey.isBlank() || oldKey.equals(newKey)) {
            return;
        }
        try {
            if (documentMapper.countByOssKeyForUser(user, oldKey) == 0) {
                quietRemove(oldKey);
            }
        } catch (RuntimeException e) {
            // 计数失败时宁可留孤儿，也不能误删另一行的正文
        }
    }

    /** 删除失败只留孤儿，可后台对账清扫；不能影响已提交的数据库结果。 */
    private void quietRemove(String key) {
        try {
            minio.removeObject(key);
        } catch (RuntimeException ignored) {
            // 行已落库；对象删除失败只留孤儿
        }
    }

    private String now() {
        return OffsetDateTime.now(ZoneOffset.UTC).toString();
    }
}
