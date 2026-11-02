package com.biopilot.catalog.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.biopilot.catalog.domain.BioDocument;
import com.biopilot.catalog.domain.BioPaper;
import com.biopilot.catalog.domain.UploadedFile;
import com.biopilot.catalog.mapper.BioDocumentMapper;
import com.biopilot.catalog.mapper.BioPaperMapper;
import com.biopilot.catalog.mapper.UploadedFileMapper;
import com.biopilot.common.core.exception.ServiceException;
import org.springframework.stereotype.Service;

/** 用户文件同名约束：论文 / 数据文件 / 文档三类共用一个名字空间。

    过渡实现按三张表逐一比对（大小写不敏感）；后续引入 `bio_user_file` 唯一键后，
    这里改为「插入冲突即 409」，不再应用层先查再插。
*/
@Service
public class FileCatalogService {

    private final BioPaperMapper paperMapper;
    private final UploadedFileMapper fileMapper;
    private final BioDocumentMapper documentMapper;

    public FileCatalogService(BioPaperMapper paperMapper, UploadedFileMapper fileMapper,
                              BioDocumentMapper documentMapper) {
        this.paperMapper = paperMapper;
        this.fileMapper = fileMapper;
        this.documentMapper = documentMapper;
    }

    /** 命中同名即抛 ServiceException；三种类型分别给用户可读文案。 */
    public void assertNameAvailable(String name) {
        assertNameAvailable(name, null, null);
    }

    /** 更新场景：跳过当前业务对象自身（按 kind + id），其余同名仍拒绝。 */
    public void assertNameAvailable(String name, String excludeKind, String excludeId) {
        String target = (name == null ? "" : name).trim().toLowerCase();
        if (target.isEmpty()) {
            return;
        }
        for (BioPaper p : paperMapper.selectList(new LambdaQueryWrapper<BioPaper>()
                .select(BioPaper::getId, BioPaper::getFileName, BioPaper::getOssKey))) {
            if ("paper".equals(excludeKind) && p.getId().equals(excludeId)) {
                continue;
            }
            String existing = p.getFileName();
            if (existing == null || existing.isBlank()) {
                existing = lastSegment(p.getOssKey());
            }
            if (existing != null && existing.trim().toLowerCase().equals(target)) {
                throw new ServiceException(409, "已存在同名文件「" + name + "」（论文），请改名后再上传");
            }
        }
        for (UploadedFile f : fileMapper.selectList(new LambdaQueryWrapper<UploadedFile>()
                .select(UploadedFile::getId, UploadedFile::getName))) {
            if ("file".equals(excludeKind) && f.getId().equals(excludeId)) {
                continue;
            }
            if (f.getName() != null && f.getName().trim().toLowerCase().equals(target)) {
                throw new ServiceException(409, "已存在同名文件「" + name + "」（数据文件），请改名后再上传");
            }
        }
        for (BioDocument d : documentMapper.selectList(new LambdaQueryWrapper<BioDocument>()
                .select(BioDocument::getId, BioDocument::getName))) {
            if ("document".equals(excludeKind) && d.getId().equals(excludeId)) {
                continue;
            }
            if (d.getName() != null && d.getName().trim().toLowerCase().equals(target)) {
                throw new ServiceException(409, "已存在同名文件「" + name + "」（文档），请改名后再上传");
            }
        }
    }

    private String lastSegment(String key) {
        if (key == null || key.isBlank()) {
            return "";
        }
        return key.substring(key.lastIndexOf('/') + 1);
    }
}
