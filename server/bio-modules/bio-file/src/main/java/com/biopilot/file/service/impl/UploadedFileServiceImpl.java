package com.biopilot.file.service.impl;

import com.biopilot.file.service.UploadedFileService;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.biopilot.file.domain.FileObjectKeys;
import com.biopilot.file.domain.UploadedFile;
import com.biopilot.file.domain.UserFileKind;
import com.biopilot.file.dto.AgentFileData;
import com.biopilot.file.dto.DownloadData;
import com.biopilot.file.dto.FileListItem;
import com.biopilot.file.dto.FileView;
import com.biopilot.file.mapper.UploadedFileMapper;
import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.common.oss.core.MinioTemplate;
import java.io.IOException;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.multipart.MultipartFile;
import com.biopilot.file.service.FileCatalogService;

/** 数据文件（对话附件）：bio_file_upload 元数据 + OSS 对象。 */
@Service
public class UploadedFileServiceImpl implements UploadedFileService {

    private static final long FILE_LIMIT = 100L * 1024 * 1024;

    private final UploadedFileMapper fileMapper;
    private final FileCatalogService catalog;
    private final MinioTemplate minio;
    private final TransactionTemplate transaction;

    public UploadedFileServiceImpl(UploadedFileMapper fileMapper, FileCatalogService catalog,
                               MinioTemplate minio,
                               PlatformTransactionManager transactionManager) {
        this.fileMapper = fileMapper;
        this.catalog = catalog;
        this.minio = minio;
        this.transaction = new TransactionTemplate(transactionManager);
    }

    public FileView upload(long userId, MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new ServiceException(422, "上传内容为空");
        }
        if (file.getSize() > FILE_LIMIT) {
            throw new ServiceException(413, "文件超过大小上限");
        }
        String name = sanitizeName(file.getOriginalFilename());
        byte[] data;
        try {
            data = file.getBytes();
        } catch (IOException e) {
            throw new ServiceException(502, "读取上传内容失败");
        }
        String fileId = UUID.randomUUID().toString().replace("-", "");
        String ossKey = FileObjectKeys.upload(String.valueOf(userId), fileId, name);
        String contentType = file.getContentType() == null
                ? "application/octet-stream" : file.getContentType();
        minio.putObject(ossKey, data, contentType);
        UploadedFile row = new UploadedFile();
        row.setId(fileId);
        row.setUserId(String.valueOf(userId));
        row.setName(name);
        row.setOssKey(ossKey);
        row.setSizeBytes((long) data.length);
        row.setContentType(contentType);
        row.setSource("upload");
        row.setCreatedAt(now());
        try {
            // 占名与业务行同事务：并发上传同名只有一个能落库
            transaction.executeWithoutResult(status -> {
                catalog.reserve(String.valueOf(userId), UserFileKind.FILE.code(), name, fileId);
                fileMapper.insert(row);
            });
        } catch (RuntimeException e) {
            try {
                minio.removeObject(ossKey);
            } catch (RuntimeException ignored) {
                // 保留原始插入错误
            }
            throw e;
        }
        return FileView.from(row);
    }

    public List<FileListItem> list(long userId) {
        return fileMapper.selectList(new QueryWrapper<UploadedFile>()
                        .orderByDesc("created_at").last("LIMIT 100"))
                .stream().map(FileListItem::from).toList();
    }

    public DownloadData download(long userId, String fileId) {
        UploadedFile row = get(fileId);
        String contentType = row.getContentType() == null || row.getContentType().isBlank()
                ? "application/octet-stream" : row.getContentType();
        return new DownloadData(minio.getObject(row.getOssKey()), row.getName(), contentType);
    }

    /**
     * 内部路径取回本人数据文件（引擎附件落盘用）。
     *
     * @param userId 归属用户（X-User-Id 透传）。
     * @param fileId 数据文件 id。
     * @return 字节 + 文件名 + MIME + OSS 键；不存在或不属于该用户时抛 404。
     */
    public AgentFileData loadForAgent(String userId, String fileId) {
        UploadedFile row = fileMapper.selectForAgent(userId, fileId);
        if (row == null) {
            throw new ServiceException(404, "文件不存在");
        }
        String contentType = row.getContentType() == null || row.getContentType().isBlank()
                ? "application/octet-stream" : row.getContentType();
        return new AgentFileData(minio.getObject(row.getOssKey()), row.getName(),
                contentType, row.getOssKey());
    }

    /**
     * agent 分析产物入库：OSS + `bio_file_upload` 行。
     *
     * <p>与用户上传不同，产物**不做同名检查**：同一次分析的图/表跨 run 重名是正常
     * 现象，不能因为上一轮的 `volcano.png` 已存在就让本轮分析失败。展示名保留原
     * 文件名，对象键用 run_id 分段隔离。</p>
     *
     * @param userId 归属用户。
     * @param runId  本次沙箱运行标识。
     * @param file   产物文件。
     * @return 已落库的文件视图。
     */
    public FileView uploadArtifact(String userId, String runId, MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new ServiceException(422, "产物内容为空");
        }
        if (file.getSize() > FILE_LIMIT) {
            throw new ServiceException(413, "文件超过大小上限");
        }
        String name = sanitizeName(file.getOriginalFilename());
        String run = safeSegment(runId);
        byte[] data;
        try {
            data = file.getBytes();
        } catch (IOException e) {
            throw new ServiceException(502, "读取产物失败");
        }
        String contentType = file.getContentType() == null
                ? "application/octet-stream" : file.getContentType();
        String fileId = UUID.randomUUID().toString().replace("-", "");
        String ossKey = FileObjectKeys.artifact(String.valueOf(userId), run, name);
        minio.putObject(ossKey, data, contentType);
        UploadedFile row = new UploadedFile();
        row.setId(fileId);
        row.setUserId(String.valueOf(userId));
        row.setName(name);
        row.setOssKey(ossKey);
        row.setSizeBytes((long) data.length);
        row.setContentType(contentType);
        // 分析产物不占名：同一张图跨 run 重名是正常现象
        row.setSource("artifact");
        row.setCreatedAt(now());
        try {
            fileMapper.insert(row);
        } catch (RuntimeException e) {
            try {
                minio.removeObject(ossKey);
            } catch (RuntimeException ignored) {
                // 保留原始插入错误
            }
            throw e;
        }
        return FileView.from(row);
    }

    public void delete(long userId, String fileId) {
        UploadedFile row = get(fileId);
        // 上传承诺了名字才需要释放；分析产物没有登记行，release 是幂等空操作
        transaction.executeWithoutResult(status -> {
            catalog.release(UserFileKind.FILE.code(), fileId);
            fileMapper.deleteById(fileId);
        });
        try {
            minio.removeObject(row.getOssKey());
        } catch (RuntimeException ignored) {
            // 行已删；对象删除失败只留孤儿
        }
    }

    private UploadedFile get(String fileId) {
        UploadedFile row = fileMapper.selectOne(new LambdaQueryWrapper<UploadedFile>()
                .eq(UploadedFile::getId, fileId));
        if (row == null) {
            throw new ServiceException(404, "文件不存在");
        }
        return row;
    }

    /** 把 run_id 归一化成可安全拼进 OSS 键的片段。 */
    private String safeSegment(String value) {
        String text = value == null ? "" : value;
        text = text.replaceAll("[\\\\/:*?\"<>|\\x00-\\x1f]", "_").trim();
        text = text.replace("..", "_");
        return text.isBlank() ? "unknown" : text;
    }

    private String sanitizeName(String name) {
        String base = name == null ? "" : name.replace('\\', '/');
        int slash = base.lastIndexOf('/');
        if (slash >= 0) {
            base = base.substring(slash + 1);
        }
        base = base.replaceAll("[\\x00-\\x1f\\\\/]", "_").trim();
        return base.isBlank() ? "data.bin" : base;
    }

    private String now() {
        return OffsetDateTime.now(ZoneOffset.UTC).toString();
    }
}
