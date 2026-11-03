package com.biopilot.file.service.impl;

import com.biopilot.file.service.PaperService;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.biopilot.file.domain.BioPaper;
import com.biopilot.file.domain.FileObjectKeys;
import com.biopilot.file.domain.UserFileKind;
import com.biopilot.file.dto.AgentFileData;
import com.biopilot.file.dto.DownloadData;
import com.biopilot.file.dto.PaperView;
import com.biopilot.file.mapper.BioPaperMapper;
import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.common.oss.core.MinioTemplate;
import com.biopilot.common.pdf.PdfMetadataExtractor;
import com.biopilot.common.web.http.AgentInternalClient;
import java.io.IOException;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.multipart.MultipartFile;
import com.biopilot.file.service.FileCatalogService;
import com.biopilot.file.service.PaperDeletionHook;
import com.biopilot.file.service.PaperMetadataHook;

/** 论文目录：bio_paper 全部列 + OSS 对象生命周期。

    索引状态列（indexed/index_status/index_error/indexed_at/chunk_count）由本服务
    维护：勾选/移出与状态复位在同一条 UPDATE 里完成，索引过程中由引擎通过
    `/internal/kb/indexing` 与 `/internal/kb/result` 触发条件更新。这样
    `bio_paper` 只有一个写者，引擎只需在状态变化后调 `/internal/kb/sync` 唤醒。

    标题是平台论文的唯一标题来源：上传时同步提取并落库，Python 索引直接从
    `bio_paper.title` 读取（不再自己解析标题）。
*/
@Service
public class PaperServiceImpl implements PaperService {

    private static final long PAPER_LIMIT = 200L * 1024 * 1024;

    private final BioPaperMapper paperMapper;
    private final FileCatalogService catalog;
    private final MinioTemplate minio;
    private final AgentInternalClient internal;
    private final PdfMetadataExtractor metadata;
    private final ObjectProvider<PaperDeletionHook> deletionHooks;
    private final ObjectProvider<PaperMetadataHook> metadataHooks;
    private final TransactionTemplate transaction;

    public PaperServiceImpl(BioPaperMapper paperMapper, FileCatalogService catalog,
                        MinioTemplate minio, AgentInternalClient internal,
                        PdfMetadataExtractor metadata,
                        ObjectProvider<PaperDeletionHook> deletionHooks,
                        ObjectProvider<PaperMetadataHook> metadataHooks,
                        PlatformTransactionManager transactionManager) {
        this.paperMapper = paperMapper;
        this.catalog = catalog;
        this.minio = minio;
        this.internal = internal;
        this.metadata = metadata;
        this.deletionHooks = deletionHooks;
        this.metadataHooks = metadataHooks;
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

    /** 登记一份 PDF（上传或文献导入）。

    标题为空时同步从 PDF 提取——知识库索引只从数据库取标题，必须在入队前落库。
    作者/年份/期刊由调用方带入（文献导入有 Europe PMC 元数据）；缺失时留空，
    加入引用库时再补。

    Args:
        userId: 归属用户。
        title: 论文标题（可为空）。
        authors: 作者（可为空）。
        year: 年份（可为空）。
        journal: 期刊（可为空）。
        fileName: 原始文件名。
        data: PDF 字节。
        contentType: 对象存储 Content-Type。
        addToKb: 是否同时加入知识库并触发索引。

    Returns:
        PaperView: 已落库的论文视图。
    */
    public PaperView ingest(long userId, String title, String authors, String year,
                            String journal, String fileName, byte[] data,
                            String contentType, boolean addToKb) {
        if (data == null || data.length == 0) {
            throw new ServiceException(422, "上传内容为空");
        }
        if (data.length > PAPER_LIMIT) {
            throw new ServiceException(413, "文件超过大小上限");
        }
        String name = sanitizeName(fileName);
        String resolvedTitle = title == null ? "" : title.trim();
        if (resolvedTitle.isEmpty()) {
            resolvedTitle = metadata.extractTitle(data);
        }
        String paperId = UUID.randomUUID().toString().replace("-", "");
        String ossKey = FileObjectKeys.paper(String.valueOf(userId), paperId, name);
        minio.putObject(ossKey, data, contentType);
        BioPaper paper = new BioPaper();
        paper.setId(paperId);
        paper.setUserId(String.valueOf(userId));
        paper.setTitle(resolvedTitle);
        paper.setAuthors(authors == null ? "" : authors);
        paper.setYear(year == null ? "" : year);
        paper.setJournal(journal == null ? "" : journal);
        paper.setFileName(name);
        paper.setOssKey(ossKey);
        paper.setSizeBytes((long) data.length);
        paper.setKbEnabled(addToKb ? 1 : 0);
        paper.setIndexStatus(addToKb ? "queued" : "not_added");
        paper.setIndexed(0);
        paper.setChunkCount(0);
        paper.setCreatedAt(now());
        try {
            // 占名与业务行同事务：唯一键冲突即整体回滚，不会留下半条记录
            transaction.executeWithoutResult(status -> {
                catalog.reserve(String.valueOf(userId), UserFileKind.PAPER.code(), name, paperId);
                paperMapper.insert(paper);
            });
        } catch (RuntimeException e) {
            // 行没落成功就别留孤儿对象；对象删除失败也只留孤儿，可后台对账
            try {
                minio.removeObject(ossKey);
            } catch (RuntimeException ignored) {
                // 对象删除失败不覆盖原始插入错误
            }
            throw e;
        }
        if (addToKb) {
            internal.kbSync(userId);
        }
        return PaperView.from(paper);
    }

    /** 预检论文文件名是否与本人已有文件重名（文献导入在下载前先挡掉）。 */
    public void assertNameAvailable(String fileName) {
        catalog.assertNameAvailable(sanitizeName(fileName));
    }

    public void register(long userId, String paperId, Map<String, Object> body) {
        String ossKey = String.valueOf(body.getOrDefault("oss_key", ""));
        if (!ossKey.startsWith("users/" + userId + "/")) {
            throw new ServiceException(422, "oss_key 必须以 users/<本人>/ 开头");
        }
        String rawName = String.valueOf(body.getOrDefault("file_name", "")).trim();
        String name = rawName.isEmpty()
                ? ossKey.substring(ossKey.lastIndexOf('/') + 1) : rawName;
        boolean addToKb = Boolean.parseBoolean(String.valueOf(body.getOrDefault("add_to_kb", "false")));
        String title = String.valueOf(body.getOrDefault("title", "")).trim();
        if (title.isEmpty() && addToKb) {
            try {
                byte[] data = minio.getObject(ossKey);
                title = metadata.extractTitle(data);
            } catch (RuntimeException ignored) {
                // 取不到原文就留空，不阻塞登记；索引侧空标题仍可切块
            }
        }
        BioPaper paper = new BioPaper();
        paper.setId(paperId);
        paper.setUserId(String.valueOf(userId));
        paper.setTitle(title);
        paper.setAuthors(String.valueOf(body.getOrDefault("authors", "")));
        paper.setYear(String.valueOf(body.getOrDefault("year", "")));
        paper.setJournal(String.valueOf(body.getOrDefault("journal", "")));
        paper.setFileName(name);
        paper.setOssKey(ossKey);
        paper.setSizeBytes(parseLong(body.get("size_bytes")));
        paper.setKbEnabled(addToKb ? 1 : 0);
        paper.setIndexStatus(addToKb ? "queued" : "not_added");
        paper.setIndexed(0);
        paper.setChunkCount(0);
        paper.setCreatedAt(now());
        // 文献导入/引擎登记：占名与写行同事务；对象已由调用方落到 OSS
        transaction.executeWithoutResult(status -> {
            catalog.reserve(String.valueOf(userId), UserFileKind.PAPER.code(), name, paperId);
            paperMapper.insert(paper);
        });
        if (addToKb) {
            internal.kbSync(userId);
        }
    }

    public List<PaperView> list(long userId) {
        return paperMapper.selectList(new QueryWrapper<BioPaper>().orderByDesc("seq"))
                .stream().map(PaperView::from).toList();
    }

    public BioPaper get(long userId, String paperId) {
        BioPaper paper = paperMapper.selectOne(new LambdaQueryWrapper<BioPaper>()
                .eq(BioPaper::getId, paperId));
        if (paper == null) {
            throw new ServiceException(404, "论文不存在");
        }
        return paper;
    }

    /** 事务内锁住论文行（加入引用库时防并发重复插入）。
     *
     * Args:
     *     userId: 归属用户。
     *     paperId: 论文 id。
     *
     * Returns:
     *     BioPaper: 加锁后的论文行。
     */
    public BioPaper getForUpdate(long userId, String paperId) {
        BioPaper paper = paperMapper.selectOne(new LambdaQueryWrapper<BioPaper>()
                .eq(BioPaper::getId, paperId).last("FOR UPDATE"));
        if (paper == null) {
            throw new ServiceException(404, "论文不存在");
        }
        return paper;
    }

    /** 写入/清空论文的引用库关联列（引用域在加入/移出时调用）。 */
    public void linkCitation(long userId, String paperId, String citationId) {
        paperMapper.update(null, new LambdaUpdateWrapper<BioPaper>()
                .eq(BioPaper::getId, paperId)
                .set(BioPaper::getCitationId, citationId));
    }

    /** 按引用库行 id 清空论文的关联列（数据库缺外键时的兜底）。 */
    public void clearCitationByCitationId(String citationId) {
        if (citationId == null || citationId.isBlank()) {
            return;
        }
        paperMapper.update(null, new LambdaUpdateWrapper<BioPaper>()
                .eq(BioPaper::getCitationId, citationId)
                .set(BioPaper::getCitationId, null));
    }

    /** 更新论文的书目字段（标题/作者/年份/期刊）；空的请求字段保持原值。

    标题变化且论文在知识库里时重新排队索引——检索块前缀/元数据用的是 DB 标题，
    改了标题必须重建该篇。引用库行由引用域在同一事务里同步更新。

    Args:
        userId: 归属用户。
        paperId: 论文 id。
        body: 允许的键 title/authors/year/journal。
    */
    public void updateMetadata(long userId, String paperId, Map<String, Object> body) {
        BioPaper paper = get(userId, paperId);
        String title = text(body, "title", paper.getTitle());
        String authors = text(body, "authors", paper.getAuthors());
        String year = text(body, "year", paper.getYear());
        String journal = text(body, "journal", paper.getJournal());
        boolean titleChanged = !Objects.equals(paper.getTitle(), title);
        boolean requeue = titleChanged && Integer.valueOf(1).equals(paper.getKbEnabled());
        transaction.executeWithoutResult(status -> {
            LambdaUpdateWrapper<BioPaper> update = new LambdaUpdateWrapper<BioPaper>()
                    .eq(BioPaper::getId, paperId)
                    .set(BioPaper::getTitle, title)
                    .set(BioPaper::getAuthors, authors)
                    .set(BioPaper::getYear, year)
                    .set(BioPaper::getJournal, journal);
            if (requeue) {
                // 标题进检索块前缀：改了标题必须重建该篇，排队交给索引器
                update.set(BioPaper::getIndexStatus, "queued")
                        .set(BioPaper::getIndexError, null);
            }
            paperMapper.update(null, update);
            metadataHooks.ifAvailable(hook -> hook.onPaperMetadataChanged(
                    paper.getCitationId(), title, authors, year, journal));
        });
        if (requeue) {
            internal.kbSync(userId);
        }
    }

    public DownloadData download(long userId, String paperId) {
        BioPaper paper = get(userId, paperId);
        byte[] data = minio.getObject(paper.getOssKey());
        String name = paper.getFileName();
        if (name == null || name.isBlank()) {
            name = paper.getOssKey().substring(paper.getOssKey().lastIndexOf('/') + 1);
        }
        return new DownloadData(data, name, "application/pdf");
    }

    /**
     * 内部路径取回论文原文（引擎索引/附件落盘用）。
     *
     * @param userId  归属用户（X-User-Id 透传）。
     * @param paperId 论文 id。
     * @return 字节 + 文件名 + MIME + OSS 键；不存在或不属于该用户时抛 404。
     */
    public AgentFileData loadForAgent(String userId, String paperId) {
        BioPaper paper = paperMapper.selectForAgent(userId, paperId);
        if (paper == null) {
            throw new ServiceException(404, "论文不存在");
        }
        String name = paper.getFileName();
        if (name == null || name.isBlank()) {
            name = paper.getOssKey().substring(paper.getOssKey().lastIndexOf('/') + 1);
        }
        byte[] data = minio.getObject(paper.getOssKey());
        return new AgentFileData(data, name, "application/pdf", paper.getOssKey());
    }

    public String delete(long userId, String paperId) {
        BioPaper paper = get(userId, paperId);
        // 行删除与引用库清理同一事务；OSS 与索引通知留在事务外（先删行、再删对象）
        transaction.executeWithoutResult(status -> {
            // 名字与业务行同事务释放：先删登记再删行，任一失败整体回滚
            catalog.release(UserFileKind.PAPER.code(), paperId);
            deletionHooks.ifAvailable(hook ->
                    hook.onPaperDeleted(userId, paperId, paper.getCitationId()));
            paperMapper.deleteById(paperId);
        });
        try {
            minio.removeObject(paper.getOssKey());
        } catch (RuntimeException ignored) {
            // 行已删；对象删除失败只留孤儿，可后台按前缀对账
        }
        internal.kbSync(userId);
        return paper.getOssKey();
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

    private String sanitizeName(String name) {
        String base = name == null ? "" : name.replace('\\', '/');
        int slash = base.lastIndexOf('/');
        if (slash >= 0) {
            base = base.substring(slash + 1);
        }
        base = base.replaceAll("[\\x00-\\x1f\\\\/]", "_").trim();
        return base.isBlank() ? "paper.pdf" : base;
    }

    private String now() {
        return OffsetDateTime.now(ZoneOffset.UTC).toString();
    }
}
