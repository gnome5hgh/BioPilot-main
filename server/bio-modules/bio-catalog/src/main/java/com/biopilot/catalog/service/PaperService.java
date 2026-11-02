package com.biopilot.catalog.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.biopilot.catalog.domain.BioPaper;
import com.biopilot.catalog.dto.DownloadData;
import com.biopilot.catalog.dto.PaperView;
import com.biopilot.catalog.mapper.BioPaperMapper;
import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.common.oss.core.MinioTemplate;
import com.biopilot.common.web.http.AgentInternalClient;
import java.io.IOException;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

/** 论文目录：bio_paper 身份/文件列 + OSS 对象生命周期。

    索引状态列（indexed/index_status/index_error/indexed_at/chunk_count）不在这里写；
    创建/删除后通过 `/internal/kb/*` 通知 Python 引擎。
*/
@Service
public class PaperService {

    private static final long PAPER_LIMIT = 200L * 1024 * 1024;

    private final BioPaperMapper paperMapper;
    private final FileCatalogService catalog;
    private final MinioTemplate minio;
    private final AgentInternalClient internal;

    public PaperService(BioPaperMapper paperMapper, FileCatalogService catalog,
                        MinioTemplate minio, AgentInternalClient internal) {
        this.paperMapper = paperMapper;
        this.catalog = catalog;
        this.minio = minio;
        this.internal = internal;
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
        return ingest(userId, "", file.getOriginalFilename(), data,
                file.getContentType() == null ? "application/pdf" : file.getContentType(), addToKb);
    }

    /** 登记一份已下载的 PDF（文献导入等外部来源）。

    标题由调用方从检索元数据带入；来源没有标题时保持空串，绝不回退文件名。

    Args:
        userId: 归属用户。
        title: 论文标题（可为空）。
        fileName: 原始文件名（用于展示与同名查重）。
        data: PDF 字节。
        contentType: 对象存储 Content-Type。
        addToKb: 是否同时加入知识库并触发索引。

    Returns:
        PaperView: 已落库的论文视图。
    */
    public PaperView ingest(long userId, String title, String fileName, byte[] data,
                            String contentType, boolean addToKb) {
        if (data == null || data.length == 0) {
            throw new ServiceException(422, "上传内容为空");
        }
        if (data.length > PAPER_LIMIT) {
            throw new ServiceException(413, "文件超过大小上限");
        }
        String name = sanitizeName(fileName);
        catalog.assertNameAvailable(name);
        String paperId = UUID.randomUUID().toString().replace("-", "");
        String ossKey = "users/" + userId + "/papers/" + paperId + "/" + name;
        minio.putObject(ossKey, data, contentType);
        BioPaper paper = new BioPaper();
        paper.setId(paperId);
        paper.setUserId(String.valueOf(userId));
        paper.setTitle(title == null ? "" : title);
        paper.setFileName(name);
        paper.setOssKey(ossKey);
        paper.setSizeBytes((long) data.length);
        paper.setIndexed(0);
        paper.setKbEnabled(addToKb ? 1 : 0);
        paper.setIndexStatus(addToKb ? "queued" : "not_added");
        paper.setChunkCount(0);
        paper.setCreatedAt(now());
        try {
            paperMapper.insert(paper);
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
            internal.kbEnqueue(userId, List.of(paperId));
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
        String name = String.valueOf(body.getOrDefault("file_name", "")).trim();
        if (name.isEmpty()) {
            name = ossKey.substring(ossKey.lastIndexOf('/') + 1);
        }
        catalog.assertNameAvailable(name);
        boolean addToKb = Boolean.parseBoolean(String.valueOf(body.getOrDefault("add_to_kb", "false")));
        BioPaper paper = new BioPaper();
        paper.setId(paperId);
        paper.setUserId(String.valueOf(userId));
        paper.setTitle(String.valueOf(body.getOrDefault("title", "")));
        paper.setFileName(name);
        paper.setOssKey(ossKey);
        paper.setSizeBytes(parseLong(body.get("size_bytes")));
        paper.setIndexed(0);
        paper.setKbEnabled(addToKb ? 1 : 0);
        paper.setIndexStatus(addToKb ? "queued" : "not_added");
        paper.setChunkCount(0);
        paper.setCreatedAt(now());
        paperMapper.insert(paper);
        if (addToKb) {
            internal.kbEnqueue(userId, List.of(paperId));
        }
    }

    public List<PaperView> list(long userId) {
        return paperMapper.selectList(new QueryWrapper<BioPaper>().orderByDesc("seq"))
                .stream().map(PaperView::from).toList();
    }

    public List<PaperView> kbList(long userId, String filter) {
        List<PaperView> papers = list(userId);
        if ("in".equals(filter)) {
            return papers.stream().filter(p -> p.kbEnabled() == 1).toList();
        }
        if ("out".equals(filter)) {
            return papers.stream().filter(p -> p.kbEnabled() == 0).toList();
        }
        return papers;
    }

    public BioPaper get(long userId, String paperId) {
        BioPaper paper = paperMapper.selectOne(new LambdaQueryWrapper<BioPaper>()
                .eq(BioPaper::getId, paperId));
        if (paper == null) {
            throw new ServiceException(404, "论文不存在");
        }
        return paper;
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

    public String delete(long userId, String paperId) {
        BioPaper paper = get(userId, paperId);
        paperMapper.deleteById(paperId);
        try {
            minio.removeObject(paper.getOssKey());
        } catch (RuntimeException ignored) {
            // 行已删；对象删除失败只留孤儿，可后台按前缀对账
        }
        internal.kbSync(userId);
        return paper.getOssKey();
    }

    public int kbAdd(long userId, List<String> paperIds) {
        int count = updateKb(paperIds, 1);
        if (!paperIds.isEmpty()) {
            internal.kbEnqueue(userId, paperIds);
        }
        return count;
    }

    public int kbRemove(long userId, List<String> paperIds) {
        int count = updateKb(paperIds, 0);
        if (!paperIds.isEmpty()) {
            internal.kbDetach(userId, paperIds);
        }
        return count;
    }

    public int kbRetry(long userId, List<String> paperIds) {
        if (!paperIds.isEmpty()) {
            internal.kbRetry(userId, paperIds);
        }
        return paperIds.size();
    }

    private int updateKb(List<String> paperIds, int enabled) {
        if (paperIds == null || paperIds.isEmpty()) {
            return 0;
        }
        return paperMapper.update(null, new LambdaUpdateWrapper<BioPaper>()
                .in(BioPaper::getId, paperIds)
                .set(BioPaper::getKbEnabled, enabled));
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
