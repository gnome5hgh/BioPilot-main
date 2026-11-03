package com.biopilot.file.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.common.oss.core.MinioTemplate;
import com.biopilot.file.domain.BioFile;
import com.biopilot.file.domain.FileNames;
import com.biopilot.file.domain.FileObjectKeys;
import com.biopilot.file.dto.DocumentSummary;
import com.biopilot.file.dto.DocumentView;
import com.biopilot.file.mapper.BioFileMapper;
import com.biopilot.file.service.DocumentService;
import com.biopilot.file.service.OssGcService;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 文档编辑器：{@code bio_file} 元数据 + OSS 正文。
 *
 * <p>正文只存在 OSS，读取以对象为准；保存时先写新版本对象，再用版本号做条件更新，
 * 提交后才删旧对象。这样并发写只有一个能成功，失败方只会留下没人引用的对象，
 * 不会出现“指针已换、正文还是旧的”或“正文已换、指针还是旧的”。</p>
 */
@Service
public class DocumentServiceImpl implements DocumentService {

    private static final int DOC_NAME_MAX = 200;
    private static final int LIST_LIMIT = 1000;

    private final BioFileMapper files;
    private final MinioTemplate minio;
    private final OssGcService gc;
    private final TransactionTemplate transaction;

    public DocumentServiceImpl(BioFileMapper files, MinioTemplate minio,
                               OssGcService gc,
                               PlatformTransactionManager transactionManager) {
        this.files = files;
        this.minio = minio;
        this.gc = gc;
        this.transaction = new TransactionTemplate(transactionManager);
    }

    public List<DocumentSummary> list(long userId) {
        return listForAgent(String.valueOf(userId));
    }

    public List<DocumentSummary> listForAgent(String userId) {
        return files.listForAgent(userId, BioFile.KIND_DOCUMENT, LIST_LIMIT)
                .stream()
                .map(d -> new DocumentSummary(d.getId(), d.getName(), d.getUpdatedAt()))
                .toList();
    }

    public Map<String, Object> create(long userId, Map<String, Object> body) {
        String name = FileNames.displayName(
                String.valueOf(body.getOrDefault("name", "新文档.md")),
                DOC_NAME_MAX, "新文档.md");
        String content = String.valueOf(body.getOrDefault("content", ""));
        String user = String.valueOf(userId);
        String id = UUID.randomUUID().toString().replace("-", "");
        byte[] data = content.getBytes(StandardCharsets.UTF_8);
        String sha = FileNames.sha256(data);
        String ossKey = FileObjectKeys.document(user, id, 1, sha, attempt());
        minio.putObject(ossKey, data, "text/markdown");
        BioFile row = newRow(user, id, name, ossKey, data, sha, 1, now());
        try {
            transaction.executeWithoutResult(status -> files.insert(row));
        } catch (DuplicateKeyException e) {
            gc.enqueue(ossKey, "compensate", 0);
            throw new ServiceException(409, "同名文件已存在，请换一个名字");
        } catch (RuntimeException e) {
            gc.enqueue(ossKey, "compensate", 0);
            throw e;
        }
        return Map.of("status", "ok", "id", id, "name", name, "version", 1);
    }

    public DocumentView get(long userId, String docId) {
        return getForAgent(String.valueOf(userId), docId);
    }

    public DocumentView getForAgent(String userId, String docId) {
        BioFile row = find(userId, docId);
        String content = readContent(userId, row);
        return new DocumentView(row.getId(), row.getName(), content,
                row.getVersion() == null ? 1 : row.getVersion(), row.getUpdatedAt());
    }

    public DocumentView getByName(String userId, String rawName) {
        String name = FileNames.displayName(rawName, DOC_NAME_MAX, "未命名.md");
        BioFile row = files.selectByNameForAgent(userId, BioFile.KIND_DOCUMENT,
                FileNames.nameKey(name));
        if (row == null) {
            throw new ServiceException(404, "文档不存在");
        }
        String content = readContent(userId, row);
        return new DocumentView(row.getId(), row.getName(), content,
                row.getVersion() == null ? 1 : row.getVersion(), row.getUpdatedAt());
    }

    public Map<String, Object> save(long userId, String docId, Map<String, Object> body) {
        String user = String.valueOf(userId);
        BioFile row = find(user, docId);
        String content = String.valueOf(body.getOrDefault("content", ""));
        String name = body.get("name") == null ? row.getName()
                : FileNames.displayName(String.valueOf(body.get("name")),
                        DOC_NAME_MAX, row.getName());
        long expected = expectedVersion(body, row);
        long nextVersion = expected + 1;
        byte[] data = content.getBytes(StandardCharsets.UTF_8);
        String sha = FileNames.sha256(data);
        String ossKey = FileObjectKeys.document(user, docId, nextVersion, sha, attempt());
        minio.putObject(ossKey, data, "text/markdown");
        Integer updated;
        try {
            updated = transaction.execute(status -> files.updateDocumentForAgent(
                    docId, user, name, FileNames.nameKey(name), ossKey, sha,
                    data.length, "text/markdown", nextVersion, now(), expected));
        } catch (DuplicateKeyException e) {
            gc.enqueue(ossKey, "compensate", 0);
            throw new ServiceException(409, "同名文件已存在，请换一个名字");
        } catch (RuntimeException e) {
            gc.enqueue(ossKey, "compensate", 0);
            throw e;
        }
        if (updated == null || updated == 0) {
            // 另一个写者已经先提交；新对象没有任何行引用，交给 GC
            gc.enqueue(ossKey, "compensate", 0);
            throw new ServiceException(409, "文档已被其他会话修改，请刷新后重试");
        }
        gc.enqueue(row.getOssKey(), "update");
        return Map.of("status", "ok", "id", docId, "name", name,
                "version", nextVersion);
    }

    /**
     * agent 成稿入库：按 (user_id, 归一化名) upsert。
     *
     * <p>新建时对象先落、行后写；已有同名文档时走条件更新（版本号来自刚读到的行）。
     * 同名目标是论文/数据文件时返回 409，不覆盖。</p>
     */
    public Map<String, Object> saveByName(String userId, String rawName, String content,
                                          Long expectedVersion) {
        String user = String.valueOf(userId);
        String name = FileNames.displayName(rawName, DOC_NAME_MAX, "未命名.md");
        String key = FileNames.nameKey(name);
        BioFile existing = files.selectByNameForAgent(user, BioFile.KIND_DOCUMENT, key);
        if (existing != null) {
            return updateExisting(user, existing, name, content, expectedVersion);
        }
        String id = UUID.randomUUID().toString().replace("-", "");
        byte[] data = content.getBytes(StandardCharsets.UTF_8);
        String sha = FileNames.sha256(data);
        String ossKey = FileObjectKeys.document(user, id, 1, sha, attempt());
        minio.putObject(ossKey, data, "text/markdown");
        BioFile row = newRow(user, id, name, ossKey, data, sha, 1, now());
        try {
            transaction.executeWithoutResult(status -> files.insert(row));
            return Map.of("status", "ok", "id", id, "name", name,
                    "version", 1, "created", true);
        } catch (DuplicateKeyException e) {
            gc.enqueue(ossKey, "compensate", 0);
            // 并发抢名：赢家若也是文档就改成更新，否则如实回冲突
            BioFile winner = files.selectByNameForAgent(user, BioFile.KIND_DOCUMENT, key);
            if (winner != null) {
                return updateExisting(user, winner, winner.getName(), content, expectedVersion);
            }
            throw new ServiceException(409, "同名文件已存在，请换一个名字");
        } catch (RuntimeException e) {
            gc.enqueue(ossKey, "compensate", 0);
            throw e;
        }
    }

    public void delete(long userId, String docId) {
        deleteForAgent(String.valueOf(userId), docId);
    }

    public void deleteForAgent(String userId, String docId) {
        BioFile row = find(userId, docId);
        transaction.executeWithoutResult(status ->
                files.deleteForAgent(docId, userId, BioFile.KIND_DOCUMENT));
        // 行已删；对象提交后交给 GC，删除失败也不会留下死行
        gc.enqueue(row.getOssKey(), "delete");
    }

    private Map<String, Object> updateExisting(String user, BioFile existing, String name,
                                               String content, Long expectedVersion) {
        long current = existing.getVersion() == null ? 1 : existing.getVersion();
        long expected = expectedVersion == null ? current : expectedVersion;
        if (expected != current) {
            // 调用方拿的是旧版本：不写对象，直接让上层刷新后重试
            throw new ServiceException(409, "文档已被其他会话修改，请刷新后重试");
        }
        long nextVersion = expected + 1;
        byte[] data = content.getBytes(StandardCharsets.UTF_8);
        String sha = FileNames.sha256(data);
        String ossKey = FileObjectKeys.document(user, existing.getId(), nextVersion, sha,
                attempt());
        minio.putObject(ossKey, data, "text/markdown");
        Integer updated;
        try {
            updated = transaction.execute(status -> files.updateDocumentForAgent(
                    existing.getId(), user, name, FileNames.nameKey(name), ossKey, sha,
                    data.length, "text/markdown", nextVersion, now(), expected));
        } catch (DuplicateKeyException e) {
            gc.enqueue(ossKey, "compensate", 0);
            throw new ServiceException(409, "同名文件已存在，请换一个名字");
        } catch (RuntimeException e) {
            gc.enqueue(ossKey, "compensate", 0);
            throw e;
        }
        if (updated == null || updated == 0) {
            gc.enqueue(ossKey, "compensate", 0);
            throw new ServiceException(409, "文档已被其他会话修改，请刷新后重试");
        }
        gc.enqueue(existing.getOssKey(), "update");
        return Map.of("status", "ok", "id", existing.getId(), "name", name,
                "version", nextVersion, "created", false);
    }

    private BioFile find(String user, String docId) {
        BioFile row = files.selectForAgent(user, BioFile.KIND_DOCUMENT, docId);
        if (row == null) {
            throw new ServiceException(404, "文档不存在");
        }
        return row;
    }

    /**
     * 读正文；旧对象被 GC 删除与读者取键之间存在竞态，404 时重读行一次。
     */
    private String readContent(String user, BioFile row) {
        try {
            return new String(minio.getObject(row.getOssKey()), StandardCharsets.UTF_8);
        } catch (RuntimeException first) {
            BioFile fresh = files.selectForAgent(user, BioFile.KIND_DOCUMENT, row.getId());
            if (fresh != null && !Objects.equals(fresh.getOssKey(), row.getOssKey())) {
                try {
                    return new String(minio.getObject(fresh.getOssKey()),
                            StandardCharsets.UTF_8);
                } catch (RuntimeException ignored) {
                    // 落到下面的统一错误
                }
            }
            throw new ServiceException(502, "文档正文读取失败，请稍后重试");
        }
    }

    private long expectedVersion(Map<String, Object> body, BioFile row) {
        Object value = body == null ? null : body.get("expected_version");
        if (value == null || String.valueOf(value).isBlank()) {
            return row.getVersion() == null ? 1 : row.getVersion();
        }
        try {
            long expected = Long.parseLong(String.valueOf(value));
            long current = row.getVersion() == null ? 1 : row.getVersion();
            if (expected != current) {
                // 调用方拿的是旧版本，直接按冲突处理，避免覆盖别人的修改
                throw new ServiceException(409, "文档已被其他会话修改，请刷新后重试");
            }
            return expected;
        } catch (NumberFormatException e) {
            throw new ServiceException(422, "expected_version 必须是整数");
        }
    }

    private BioFile newRow(String user, String id, String name, String ossKey,
                           byte[] data, String sha, long version, String now) {
        BioFile row = new BioFile();
        row.setId(id);
        row.setUserId(user);
        row.setKind(BioFile.KIND_DOCUMENT);
        row.setName(name);
        row.setNameKey(FileNames.nameKey(name));
        row.setOssKey(ossKey);
        row.setSizeBytes((long) data.length);
        row.setContentType("text/markdown");
        row.setSha256(sha);
        row.setVersion(version);
        row.setSource("document");
        row.setCreatedAt(now);
        row.setUpdatedAt(now);
        return row;
    }

    private String now() {
        return FileNames.now();
    }

    /** 每次写入的尝试标识：让并发写者各自落在不同对象键上。 */
    private String attempt() {
        return UUID.randomUUID().toString().replace("-", "").substring(0, 8);
    }
}
