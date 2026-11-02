package com.biopilot.catalog.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.biopilot.catalog.domain.UploadedFile;
import com.biopilot.catalog.dto.DownloadData;
import com.biopilot.catalog.dto.FileListItem;
import com.biopilot.catalog.dto.FileView;
import com.biopilot.catalog.mapper.UploadedFileMapper;
import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.common.oss.core.MinioTemplate;
import java.io.IOException;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

/** 数据文件（对话附件）：bio_file_upload 元数据 + OSS 对象。 */
@Service
public class UploadedFileService {

    private static final long FILE_LIMIT = 100L * 1024 * 1024;

    private final UploadedFileMapper fileMapper;
    private final FileCatalogService catalog;
    private final MinioTemplate minio;

    public UploadedFileService(UploadedFileMapper fileMapper, FileCatalogService catalog,
                               MinioTemplate minio) {
        this.fileMapper = fileMapper;
        this.catalog = catalog;
        this.minio = minio;
    }

    public FileView upload(long userId, MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw new ServiceException(422, "上传内容为空");
        }
        if (file.getSize() > FILE_LIMIT) {
            throw new ServiceException(413, "文件超过大小上限");
        }
        String name = sanitizeName(file.getOriginalFilename());
        catalog.assertNameAvailable(name);
        byte[] data;
        try {
            data = file.getBytes();
        } catch (IOException e) {
            throw new ServiceException(502, "读取上传内容失败");
        }
        String fileId = UUID.randomUUID().toString().replace("-", "");
        String ossKey = "users/" + userId + "/files/uploads/" + fileId + "/" + name;
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

    public void delete(long userId, String fileId) {
        UploadedFile row = get(fileId);
        fileMapper.deleteById(fileId);
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
