package com.biopilot.file.service.impl;

import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.common.oss.core.MinioTemplate;
import com.biopilot.file.domain.BioFile;
import com.biopilot.file.domain.FileNames;
import com.biopilot.file.domain.FileObjectKeys;
import com.biopilot.file.dto.AgentFileData;
import com.biopilot.file.dto.DownloadData;
import com.biopilot.file.dto.FileListItem;
import com.biopilot.file.dto.FileView;
import com.biopilot.file.mapper.BioFileMapper;
import com.biopilot.file.service.OssGcService;
import com.biopilot.file.service.UploadedFileService;
import java.io.IOException;
import java.util.List;
import java.util.UUID;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.multipart.MultipartFile;

/** 数据文件（对话附件/分析产物）：bio_file 的 data/artifact 行 + OSS 对象。 */
@Service
public class UploadedFileServiceImpl implements UploadedFileService {

    private static final long FILE_LIMIT = 100L * 1024 * 1024;
    private static final int LIST_LIMIT = 100;

    private final BioFileMapper files;
    private final MinioTemplate minio;
    private final OssGcService gc;
    private final TransactionTemplate transaction;

    public UploadedFileServiceImpl(BioFileMapper files, MinioTemplate minio,
                                   OssGcService gc,
                                   PlatformTransactionManager transactionManager) {
        this.files = files;
        this.minio = minio;
        this.gc = gc;
        this.transaction = new TransactionTemplate(transactionManager);
    }

    public FileView upload(long userId, MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new ServiceException(422, "上传内容为空");
        }
        if (file.getSize() > FILE_LIMIT) {
            throw new ServiceException(413, "文件超过大小上限");
        }
        String name = FileNames.displayName(file.getOriginalFilename(), 255, "data.bin");
        byte[] data = read(file, "读取上传内容失败");
        String contentType = file.getContentType() == null
                ? "application/octet-stream" : file.getContentType();
        String user = String.valueOf(userId);
        String fileId = UUID.randomUUID().toString().replace("-", "");
        String ossKey = FileObjectKeys.upload(user, fileId, name);
        minio.putObject(ossKey, data, contentType);
        BioFile row = newRow(user, fileId, BioFile.KIND_DATA, name,
                FileNames.nameKey(name), ossKey, data, contentType, null);
        row.setSource("upload");
        try {
            transaction.executeWithoutResult(status -> files.insert(row));
        } catch (DuplicateKeyException e) {
            gc.enqueue(ossKey, "compensate", 0);
            throw new ServiceException(409, "同名文件已存在: " + name);
        } catch (RuntimeException e) {
            gc.enqueue(ossKey, "compensate", 0);
            throw e;
        }
        return FileView.from(row);
    }

    public List<FileListItem> list(long userId) {
        return files.listDataForAgent(String.valueOf(userId), LIST_LIMIT)
                .stream().map(FileListItem::from).toList();
    }

    public List<FileListItem> listForAgent(String userId, int limit) {
        return files.listDataForAgent(userId, limit)
                .stream().map(FileListItem::from).toList();
    }

    public List<FileListItem> listByRun(String userId, String runId, int limit) {
        return files.listByRunForAgent(userId, runId, limit)
                .stream().map(FileListItem::from).toList();
    }

    public DownloadData download(long userId, String fileId) {
        BioFile row = get(userId, fileId);
        String contentType = contentType(row);
        return new DownloadData(minio.getObject(row.getOssKey()), row.getName(), contentType);
    }

    public AgentFileData loadForAgent(String userId, String fileId) {
        BioFile row = files.selectDataForAgent(userId, fileId);
        if (row == null) {
            throw new ServiceException(404, "文件不存在");
        }
        return new AgentFileData(minio.getObject(row.getOssKey()), row.getName(),
                contentType(row), row.getOssKey(), row.getSha256(),
                row.getVersion() == null ? 1 : row.getVersion(), row.getKind());
    }

    /**
     * agent 分析产物入库：kind=artifact，不占用户可见名字。
     *
     * <p>对象键带 fileId，同一 run 下两次同名产物会落到不同键，不再互相覆盖。</p>
     */
    public FileView uploadArtifact(String userId, String runId, MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new ServiceException(422, "产物内容为空");
        }
        if (file.getSize() > FILE_LIMIT) {
            throw new ServiceException(413, "文件超过大小上限");
        }
        String name = FileNames.displayName(file.getOriginalFilename(), 255, "artifact.bin");
        byte[] data = read(file, "读取产物失败");
        String contentType = file.getContentType() == null
                ? "application/octet-stream" : file.getContentType();
        String user = String.valueOf(userId);
        String fileId = UUID.randomUUID().toString().replace("-", "");
        String ossKey = FileObjectKeys.artifact(user, runId, fileId, name);
        minio.putObject(ossKey, data, contentType);
        BioFile row = newRow(user, fileId, BioFile.KIND_ARTIFACT, name,
                null, ossKey, data, contentType, runId);
        row.setSource("artifact");
        try {
            files.insert(row);
        } catch (RuntimeException e) {
            gc.enqueue(ossKey, "compensate", 0);
            throw e;
        }
        return FileView.from(row);
    }

    public void delete(long userId, String fileId) {
        deleteForAgent(String.valueOf(userId), fileId);
    }

    public void deleteForAgent(String userId, String fileId) {
        BioFile row = getForAgent(userId, fileId);
        transaction.executeWithoutResult(status -> files.deleteForAgent(
                fileId, userId, row.getKind()));
        // 行已删；对象提交后交给 GC
        gc.enqueue(row.getOssKey(), "delete");
    }

    private BioFile get(long userId, String fileId) {
        return getForAgent(String.valueOf(userId), fileId);
    }

    private BioFile getForAgent(String userId, String fileId) {
        BioFile row = files.selectDataForAgent(userId, fileId);
        if (row == null) {
            throw new ServiceException(404, "文件不存在");
        }
        return row;
    }

    private BioFile newRow(String user, String fileId, String kind, String name,
                           String nameKey, String ossKey, byte[] data,
                           String contentType, String runId) {
        BioFile row = new BioFile();
        row.setId(fileId);
        row.setUserId(user);
        row.setKind(kind);
        row.setName(name);
        row.setNameKey(nameKey);
        row.setOssKey(ossKey);
        row.setSizeBytes((long) data.length);
        row.setContentType(contentType);
        row.setSha256(FileNames.sha256(data));
        row.setVersion(1L);
        row.setRunId(runId);
        row.setCreatedAt(FileNames.now());
        row.setUpdatedAt(FileNames.now());
        return row;
    }

    private byte[] read(MultipartFile file, String message) {
        try {
            return file.getBytes();
        } catch (IOException e) {
            throw new ServiceException(502, message);
        }
    }

    private String contentType(BioFile row) {
        return row.getContentType() == null || row.getContentType().isBlank()
                ? "application/octet-stream" : row.getContentType();
    }
}
