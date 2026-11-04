package com.biopilot.file.service.impl;

import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.common.oss.core.MinioTemplate;
import com.biopilot.common.pdf.PdfMetadataExtractor;
import com.biopilot.common.web.http.AgentInternalClient;
import com.biopilot.file.domain.BioFile;
import com.biopilot.file.domain.FileNames;
import com.biopilot.file.domain.FileObjectKeys;
import com.biopilot.file.domain.UserFileKind;
import com.biopilot.file.dto.AgentFileData;
import com.biopilot.file.dto.DownloadData;
import com.biopilot.file.dto.PaperView;
import com.biopilot.file.mapper.BioFileMapper;
import com.biopilot.file.service.OssGcService;
import com.biopilot.file.service.PaperDeletionHook;
import com.biopilot.file.service.PaperMetadataHook;
import com.biopilot.file.service.PaperRequeueHook;
import com.biopilot.file.service.PaperService;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.multipart.MultipartFile;

/**
 * 论文目录：{@code bio_file} 的 paper 行 + OSS 对象生命周期。
 *
 * <p>论文正文不可变，对象键按 paperId 固定；元数据与索引状态都在同一行上，
 * 身份/文件/书目列由本服务写，index_* 列由 bio-kb 写。创建走“对象先落、行后写”，
 * 删除走“行先删、对象交给 GC”。</p>
 */
@Service
public class PaperServiceImpl implements PaperService {

    private static final long PAPER_LIMIT = 200L * 1024 * 1024;
    private static final int LIST_LIMIT = 1000;

    private final BioFileMapper files;
    private final MinioTemplate minio;
    private final OssGcService gc;
    private final AgentInternalClient internal;
    private final PdfMetadataExtractor metadata;
    private final ObjectProvider<PaperDeletionHook> deletionHooks;
    private final ObjectProvider<PaperMetadataHook> metadataHooks;
    private final ObjectProvider<PaperRequeueHook> requeueHooks;
    private final TransactionTemplate transaction;

    public PaperServiceImpl(BioFileMapper files, MinioTemplate minio, OssGcService gc,
                            AgentInternalClient internal, PdfMetadataExtractor metadata,
                            ObjectProvider<PaperDeletionHook> deletionHooks,
                            ObjectProvider<PaperMetadataHook> metadataHooks,
                            ObjectProvider<PaperRequeueHook> requeueHooks,
                            PlatformTransactionManager transactionManager) {
        this.files = files;
        this.minio = minio;
        this.gc = gc;
        this.internal = internal;
        this.metadata = metadata;
        this.deletionHooks = deletionHooks;
        this.metadataHooks = metadataHooks;
        this.requeueHooks = requeueHooks;
        this.transaction = new TransactionTemplate(transactionManager);
    }

    public PaperView create(long userId, MultipartFile file, boolean addToKb) {
        if (file == null || file.isEmpty()) {
            throw new ServiceException(422, "上传内容为空");
        }
        if (file.getSize() > PAPER_LIMIT) {
            throw new ServiceException(413, "文件超过大小上限");
        }
        byte[] data;
        try {
            data = file.getBytes();
        } catch (IOException e) {
            throw new ServiceException(502, "读取上传内容失败");
        }
        String contentType = file.getContentType() == null
                ? "application/pdf" : file.getContentType();
        return ingest(userId, "", "", "", "", file.getOriginalFilename(), data,
                contentType, addToKb);
    }

    public PaperView ingest(long userId, String title, String authors, String year,
                            String journal, String fileName, byte[] data,
                            String contentType, boolean addToKb) {
        if (data == null || data.length == 0) {
            throw new ServiceException(422, "上传内容为空");
        }
        if (data.length > PAPER_LIMIT) {
            throw new ServiceException(413, "文件超过大小上限");
        }
        String name = FileNames.displayName(fileName, 255, "paper.pdf");
        String resolvedTitle = title == null ? "" : title.trim();
        if (resolvedTitle.isEmpty()) {
            resolvedTitle = metadata.extractTitle(data);
        }
        String user = String.valueOf(userId);
        String paperId = UUID.randomUUID().toString().replace("-", "");
        String ossKey = FileObjectKeys.paper(user, paperId, name);
        minio.putObject(ossKey, data, contentType);
        BioFile row = newPaperRow(user, paperId, name, ossKey, data.length,
                contentType, resolvedTitle, authors, year, journal, addToKb);
        try {
            transaction.executeWithoutResult(status -> files.insert(row));
        } catch (DuplicateKeyException e) {
            gc.enqueue(ossKey, "compensate", 0);
            throw nameConflict(name);
        } catch (RuntimeException e) {
            gc.enqueue(ossKey, "compensate", 0);
            throw e;
        }
        if (addToKb) {
            internal.kbSync(userId);
        }
        return PaperView.from(row);
    }

    public void assertNameAvailable(long userId, String fileName) {
        String name = FileNames.displayName(fileName, 255, "paper.pdf");
        BioFile existing = files.selectAnyByNameForAgent(
                String.valueOf(userId), FileNames.nameKey(name));
        if (existing != null) {
            throw nameConflict(name, existing.getKind());
        }
    }

    public void register(long userId, String paperId, Map<String, Object> body) {
        String user = String.valueOf(userId);
        String ossKey = String.valueOf(body.getOrDefault("oss_key", ""));
        if (!ossKey.startsWith("users/" + user + "/")) {
            throw new ServiceException(422, "oss_key 必须以 users/<本人>/ 开头");
        }
        String rawName = String.valueOf(body.getOrDefault("file_name", "")).trim();
        String name = rawName.isEmpty()
                ? ossKey.substring(ossKey.lastIndexOf('/') + 1) : rawName;
        name = FileNames.displayName(name, 255, "paper.pdf");
        boolean addToKb = Boolean.parseBoolean(
                String.valueOf(body.getOrDefault("add_to_kb", "false")));
        String title = String.valueOf(body.getOrDefault("title", "")).trim();
        BioFile row = newPaperRow(user, paperId, name, ossKey,
                parseLong(body.get("size_bytes")), "application/pdf", title,
                String.valueOf(body.getOrDefault("authors", "")),
                String.valueOf(body.getOrDefault("year", "")),
                String.valueOf(body.getOrDefault("journal", "")), addToKb);
        try {
            transaction.executeWithoutResult(status -> files.insert(row));
        } catch (DuplicateKeyException e) {
            throw nameConflict(name);
        }
        if (addToKb) {
            internal.kbSync(userId);
        }
    }

    public List<PaperView> list(long userId) {
        return files.listForAgent(String.valueOf(userId), BioFile.KIND_PAPER, LIST_LIMIT)
                .stream().map(PaperView::from).toList();
    }

    public BioFile get(long userId, String paperId) {
        BioFile paper = files.selectForAgent(String.valueOf(userId),
                BioFile.KIND_PAPER, paperId);
        if (paper == null) {
            throw new ServiceException(404, "论文不存在");
        }
        return paper;
    }

    public BioFile getForUpdate(long userId, String paperId) {
        BioFile paper = files.selectPaperForUpdate(String.valueOf(userId), paperId);
        if (paper == null) {
            throw new ServiceException(404, "论文不存在");
        }
        return paper;
    }

    public void linkCitation(long userId, String paperId, String citationId) {
        files.updateCitationForAgent(paperId, String.valueOf(userId), citationId);
    }

    public void clearCitationByCitationId(String citationId) {
        if (citationId == null || citationId.isBlank()) {
            return;
        }
        files.clearCitationByCitationId(citationId);
    }

    public void updateMetadata(long userId, String paperId, Map<String, Object> body) {
        BioFile paper = get(userId, paperId);
        String title = text(body, "title", paper.getTitle());
        String authors = text(body, "authors", paper.getAuthors());
        String year = text(body, "year", paper.getYear());
        String journal = text(body, "journal", paper.getJournal());
        boolean titleChanged = !Objects.equals(paper.getTitle(), title);
        boolean requeue = titleChanged && Integer.valueOf(1).equals(paper.getKbEnabled());
        transaction.executeWithoutResult(status -> {
            // 只写 bio-file owns 的书目列；index_* 由 bio-kb 独占写。
            files.updatePaperMetadataForAgent(paperId, String.valueOf(userId), title,
                    authors, year, journal, now());
            metadataHooks.ifAvailable(hook -> hook.onPaperMetadataChanged(
                    paper.getCitationId(), title, authors, year, journal));
        });
        if (requeue) {
            // 标题进检索块前缀：由 bio-kb 负责重排索引并唤醒引擎
            requeueHooks.ifAvailable(hook -> hook.onPaperTitleChanged(userId, paperId));
        }
    }

    public DownloadData download(long userId, String paperId) {
        BioFile paper = get(userId, paperId);
        byte[] data = minio.getObject(paper.getOssKey());
        String name = paper.getName();
        if (name == null || name.isBlank()) {
            name = paper.getOssKey().substring(paper.getOssKey().lastIndexOf('/') + 1);
        }
        return new DownloadData(data, name, "application/pdf");
    }

    public AgentFileData loadForAgent(String userId, String paperId) {
        BioFile paper = files.selectForAgent(userId, BioFile.KIND_PAPER, paperId);
        if (paper == null) {
            throw new ServiceException(404, "论文不存在");
        }
        String name = paper.getName();
        if (name == null || name.isBlank()) {
            name = paper.getOssKey().substring(paper.getOssKey().lastIndexOf('/') + 1);
        }
        byte[] data = minio.getObject(paper.getOssKey());
        return new AgentFileData(data, name, "application/pdf", paper.getOssKey(),
                paper.getSha256(), paper.getVersion() == null ? 1 : paper.getVersion(),
                BioFile.KIND_PAPER);
    }

    public String delete(long userId, String paperId) {
        BioFile paper = get(userId, paperId);
        transaction.executeWithoutResult(status -> {
            deletionHooks.ifAvailable(hook ->
                    hook.onPaperDeleted(userId, paperId, paper.getCitationId()));
            files.deleteForAgent(paperId, String.valueOf(userId), BioFile.KIND_PAPER);
        });
        // 行已删；对象提交后交给 GC，删除失败也不会留下死行
        gc.enqueue(paper.getOssKey(), "delete");
        internal.kbSync(userId);
        return paper.getOssKey();
    }

    private BioFile newPaperRow(String user, String paperId, String name, String ossKey,
                                long size, String contentType, String title,
                                String authors, String year, String journal,
                                boolean addToKb) {
        BioFile row = new BioFile();
        row.setId(paperId);
        row.setUserId(user);
        row.setKind(BioFile.KIND_PAPER);
        row.setName(name);
        row.setNameKey(FileNames.nameKey(name));
        row.setOssKey(ossKey);
        row.setSizeBytes(size);
        row.setContentType(contentType);
        row.setVersion(1L);
        row.setSource("paper");
        row.setTitle(title == null ? "" : title);
        row.setAuthors(authors == null ? "" : authors);
        row.setYear(year == null ? "" : year);
        row.setJournal(journal == null ? "" : journal);
        row.setKbEnabled(addToKb ? 1 : 0);
        row.setIndexed(0);
        row.setIndexStatus(addToKb ? "queued" : "not_added");
        row.setChunkCount(0);
        row.setCreatedAt(now());
        row.setUpdatedAt(now());
        return row;
    }

    private ServiceException nameConflict(String name) {
        return nameConflict(name, null);
    }

    private ServiceException nameConflict(String name, String kind) {
        String type = kind == null || kind.isBlank() ? "文件" : UserFileKind.labelOf(kind);
        return new ServiceException(409, "同名" + type + "已存在: " + name);
    }

    private String text(Map<String, Object> body, String key, String fallback) {
        if (body == null || !body.containsKey(key)) {
            return fallback == null ? "" : fallback;
        }
        Object value = body.get(key);
        return value == null ? "" : String.valueOf(value).trim();
    }

    private long parseLong(Object value) {
        try {
            return Long.parseLong(String.valueOf(value == null ? "0" : value));
        } catch (NumberFormatException e) {
            return 0L;
        }
    }

    private String now() {
        return FileNames.now();
    }
}
