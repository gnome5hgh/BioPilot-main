package com.biopilot.file.service.impl;

import com.biopilot.common.oss.core.MinioTemplate;
import com.biopilot.file.domain.BioDocument;
import com.biopilot.file.domain.BioPaper;
import com.biopilot.file.domain.BioUserFile;
import com.biopilot.file.domain.FileObjectKeys;
import com.biopilot.file.domain.UploadedFile;
import com.biopilot.file.domain.UserFileKind;
import com.biopilot.file.mapper.BioDocumentMapper;
import com.biopilot.file.mapper.BioPaperMapper;
import com.biopilot.file.mapper.BioUserFileMapper;
import com.biopilot.file.mapper.UploadedFileMapper;
import com.biopilot.file.service.FileCatalogService;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 启动回填：把存量论文/上传文件/文档登记进 {@code bio_user_file}。
 *
 * <p>登记表是唯一键约束的载体，上线前已存在的业务行必须先补登记，否则它们既不
 * 受同名约束保护、也无法被新路径查到。并发期产生的同名重复行会在这里被改成
 * {@code 原名 (2).ext} 并逐条写日志；文档的旧名字基对象键同时迁到 id 基键。</p>
 *
 * <p>幂等：登记行数与业务行数一致时不会写库；失败只记日志，不阻塞启动
 * （下次启动重试）。分析产物（source=artifact）不参与。</p>
 */
@Component
public class UserFileCatalogBackfillRunner implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(UserFileCatalogBackfillRunner.class);

    /** 同名替名的尝试上限；超过说明数据异常，跳过并留日志。 */
    private static final int MAX_SUFFIX = 1000;

    private final BioUserFileMapper catalogMapper;
    private final BioPaperMapper paperMapper;
    private final UploadedFileMapper fileMapper;
    private final BioDocumentMapper documentMapper;
    private final FileCatalogService catalog;
    private final MinioTemplate minio;
    private final TransactionTemplate transaction;

    public UserFileCatalogBackfillRunner(BioUserFileMapper catalogMapper,
                                         BioPaperMapper paperMapper,
                                         UploadedFileMapper fileMapper,
                                         BioDocumentMapper documentMapper,
                                         FileCatalogService catalog,
                                         MinioTemplate minio,
                                         PlatformTransactionManager transactionManager) {
        this.catalogMapper = catalogMapper;
        this.paperMapper = paperMapper;
        this.fileMapper = fileMapper;
        this.documentMapper = documentMapper;
        this.catalog = catalog;
        this.minio = minio;
        this.transaction = new TransactionTemplate(transactionManager);
    }

    @Override
    public void run(ApplicationArguments args) {
        try {
            backfill();
        } catch (RuntimeException e) {
            log.warn("用户文件名登记回填失败（下次启动重试）: {}", e.getMessage(), e);
        }
    }

    /** 回填入口：按「论文 → 上传文件 → 文档」顺序占名，先到先得。 */
    void backfill() {
        Set<String> registered = registeredRefs();
        registerPapers(registered);
        registerFiles(registered);
        registerDocuments(registered);
    }

    private Set<String> registeredRefs() {
        List<BioUserFile> rows = catalogMapper.selectAllForBackfill();
        Set<String> refs = new HashSet<>();
        for (BioUserFile row : rows) {
            refs.add(key(row.getKind(), row.getRefId()));
        }
        return refs;
    }

    private void registerPapers(Set<String> registered) {
        for (BioPaper paper : paperMapper.selectAllForCatalogBackfill()) {
            String name = paper.getFileName();
            if (name == null || name.isBlank()) {
                continue;   // 没有展示名就没有可占的名字
            }
            String ref = key(UserFileKind.PAPER.code(), paper.getId());
            if (registered.contains(ref)) {
                continue;
            }
            // 占名与改名同事务：半途失败会留下一半登记一半旧名
            transaction.executeWithoutResult(status -> {
                String finalName = reserve(paper.getUserId(), UserFileKind.PAPER.code(),
                        name, paper.getId(), ref, registered);
                if (!finalName.equals(name)) {
                    paperMapper.updateFileNameForCatalogBackfill(paper.getId(), finalName);
                }
            });
        }
    }

    private void registerFiles(Set<String> registered) {
        for (UploadedFile file : fileMapper.selectAllForCatalogBackfill()) {
            String name = file.getName();
            if (name == null || name.isBlank()) {
                continue;
            }
            String ref = key(UserFileKind.FILE.code(), file.getId());
            if (registered.contains(ref)) {
                continue;
            }
            transaction.executeWithoutResult(status -> {
                String finalName = reserve(file.getUserId(), UserFileKind.FILE.code(),
                        name, file.getId(), ref, registered);
                if (!finalName.equals(name)) {
                    fileMapper.updateNameForCatalogBackfill(file.getId(), finalName);
                }
            });
        }
    }

    private void registerDocuments(Set<String> registered) {
        for (BioDocument doc : documentMapper.selectAllForCatalogBackfill()) {
            String name = doc.getName();
            if (name == null || name.isBlank()) {
                log.warn("文档没有名字，跳过登记 id={}", doc.getId());
                continue;
            }
            String user = doc.getUserId();
            String ref = key(UserFileKind.DOCUMENT.code(), doc.getId());
            // 对象先落（事务外）：旧的名字基键可能被同名行共用，复制到 id 基键
            String oldKey = doc.getOssKey();
            String newKey = FileObjectKeys.document(user, doc.getId());
            String targetKey = oldKey;
            if (oldKey != null && !oldKey.equals(newKey)) {
                byte[] data = readDocument(doc, oldKey);
                if (data == null) {
                    log.warn("文档对象缺失，只改名不迁键 id={} key={}", doc.getId(), oldKey);
                } else {
                    try {
                        minio.putObject(newKey, data, "text/markdown");
                        targetKey = newKey;
                    } catch (RuntimeException e) {
                        log.warn("文档对象键迁移失败 id={}: {}", doc.getId(), e.getMessage());
                    }
                }
            }
            final String finalKey = targetKey;
            transaction.executeWithoutResult(status -> {
                String finalName = registered.contains(ref) ? name
                        : reserve(user, UserFileKind.DOCUMENT.code(), name,
                                doc.getId(), ref, registered);
                if (!finalName.equals(name)) {
                    log.warn("文档同名冲突，已改名为 {}（原 {}，ref={}）",
                            finalName, name, doc.getId());
                }
                if (!java.util.Objects.equals(finalKey, oldKey) || !finalName.equals(name)) {
                    documentMapper.updateForCatalogBackfill(
                            doc.getId(), finalName, finalKey, now());
                    // 旧键可能仍被尚未迁移的同名行共用，这里不删，留给后台对账
                }
            });
        }
    }

    /**
     * 占名；撞名就给落败者生成 {@code 原名 (n).ext} 的新名字并占住它。
     *
     * @return 最终使用的名字（可能与入参不同）
     */
    private String reserve(String userId, String kind, String name, String refId,
                           String ref, Set<String> registered) {
        if (catalogMapper.insertIgnore(registryRow(userId, kind, name, refId)) == 1) {
            registered.add(ref);
            return name;
        }
        int dot = name.lastIndexOf('.');
        String stem = dot > 0 ? name.substring(0, dot) : name;
        String ext = dot > 0 ? name.substring(dot) : "";
        for (int n = 2; n <= MAX_SUFFIX; n++) {
            String suffix = " (" + n + ")" + ext;
            int maxStem = 255 - suffix.length();
            String safeStem = stem.length() > maxStem && maxStem > 0
                    ? stem.substring(0, maxStem) : stem;
            String candidate = safeStem + suffix;
            if (catalogMapper.insertIgnore(registryRow(userId, kind, candidate, refId)) == 1) {
                registered.add(ref);
                log.warn("{} 文件名重复，已改名为 {}（原 {}，ref={}）",
                        UserFileKind.labelOf(kind), candidate, name, refId);
                return candidate;
            }
        }
        // 连续 999 个候选都被占：保留原名，唯一键继续兜底（下次启动重试）
        log.error("{} 文件名无法生成唯一替名（原 {}，ref={}）",
                UserFileKind.labelOf(kind), name, refId);
        return name;
    }

    private byte[] readDocument(BioDocument doc, String oldKey) {
        try {
            return minio.getObject(oldKey);
        } catch (RuntimeException e) {
            String content = doc.getContent() == null ? "" : doc.getContent();
            if (content.isEmpty()) {
                return null;
            }
            return content.getBytes(StandardCharsets.UTF_8);
        }
    }

    private BioUserFile registryRow(String userId, String kind, String name, String refId) {
        BioUserFile row = new BioUserFile();
        row.setUserId(userId);
        row.setKind(kind);
        row.setNameKey(catalog.nameKey(name));
        row.setName(name);
        row.setRefId(refId);
        row.setCreatedAt(now());
        return row;
    }

    private static String key(String kind, String refId) {
        return kind + ":" + refId;
    }

    private static String now() {
        return OffsetDateTime.now(ZoneOffset.UTC).toString();
    }
}
