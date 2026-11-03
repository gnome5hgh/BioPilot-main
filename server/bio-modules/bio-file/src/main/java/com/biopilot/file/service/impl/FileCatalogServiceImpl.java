package com.biopilot.file.service.impl;

import com.biopilot.file.service.FileCatalogService;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.file.domain.BioUserFile;
import com.biopilot.file.mapper.BioUserFileMapper;
import java.text.Normalizer;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Locale;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;

/**
 * 用户文件同名约束：以 {@code bio_user_file} 的唯一键为准。
 *
 * <p>创建路径「先占名再写业务行」，两者由调用方放在同一事务里；冲突时由数据库
 * 唯一键拒绝，应用层不再逐表扫描比对，也不会因为并发先查后插产生重复行。</p>
 */
@Service
public class FileCatalogServiceImpl implements FileCatalogService {

    /** 与 DDL 的 name_key / name 列宽一致。 */
    private static final int MAX_NAME_LENGTH = 255;

    private final BioUserFileMapper mapper;

    public FileCatalogServiceImpl(BioUserFileMapper mapper) {
        this.mapper = mapper;
    }

    @Override
    public void assertNameAvailable(String name) {
        assertNameAvailable(name, null, null);
    }

    @Override
    public void assertNameAvailable(String name, String excludeKind, String excludeRefId) {
        String key = nameKey(name);
        BioUserFile existing = mapper.selectOne(new LambdaQueryWrapper<BioUserFile>()
                .eq(BioUserFile::getNameKey, key)
                .last("LIMIT 1"));
        if (existing == null) {
            return;
        }
        boolean self = excludeKind != null && excludeRefId != null
                && excludeKind.equals(existing.getKind())
                && excludeRefId.equals(existing.getRefId());
        if (!self) {
            throw FileCatalogService.conflict(name.trim(), existing.getKind());
        }
    }

    @Override
    public void reserve(String userId, String kind, String name, String refId) {
        String display = trimmed(name);
        String key = nameKey(display);
        BioUserFile row = newRow(userId, kind, key, display, refId);
        // 不能依赖 affected rows：Connector/J 默认 CLIENT_FOUND_ROWS，
        // ON DUPLICATE KEY UPDATE 命中已有行时也返回 1。以「插完再读」为准：
        // 读到的 ref 是自己 → 占名成功（或幂等重试）；是别人 → 冲突。
        mapper.tryReserve(row);
        BioUserFile current = mapper.selectByNameKeyForUser(userId, key);
        if (current != null && kind.equals(current.getKind())
                && refId.equals(current.getRefId())) {
            return;     // 本次插入成功，或同一对象幂等重试
        }
        throw FileCatalogService.conflict(display, current == null ? "" : current.getKind());
    }

    @Override
    public Reservation find(String userId, String name) {
        BioUserFile row = mapper.selectByNameKeyForUser(userId, nameKey(name));
        return row == null ? null : new Reservation(row.getKind(), row.getRefId(), row.getName());
    }

    @Override
    public void rename(String userId, String kind, String refId, String newName) {
        String display = trimmed(newName);
        String key = nameKey(display);
        int updated;
        try {
            updated = mapper.update(null, new LambdaUpdateWrapper<BioUserFile>()
                    .eq(BioUserFile::getKind, kind)
                    .eq(BioUserFile::getRefId, refId)
                    .set(BioUserFile::getNameKey, key)
                    .set(BioUserFile::getName, display));
        } catch (DuplicateKeyException e) {
            // 唯一键是最终裁决：并发改名撞上同一个名字时，后到者回 409
            BioUserFile existing = mapper.selectByNameKeyForUser(userId, key);
            throw FileCatalogService.conflict(
                    display, existing == null ? "" : existing.getKind());
        }
        if (updated == 0) {
            // 存量行可能尚未回填（启动修复失败/旧进程写入）：在改名处补登记一次
            mapper.insertIgnore(newRow(userId, kind, key, display, refId));
            BioUserFile current = mapper.selectByNameKeyForUser(userId, key);
            if (current == null || !kind.equals(current.getKind())
                    || !refId.equals(current.getRefId())) {
                throw FileCatalogService.conflict(
                        display, current == null ? "" : current.getKind());
            }
        }
    }

    @Override
    public void release(String userId, String kind, String refId) {
        // 显式 user_id：agent 成稿更新没有登录态，不能依赖租户插件
        mapper.deleteByUserAndRef(userId, kind, refId);
    }

    @Override
    public String nameKey(String name) {
        String text = trimmed(name);
        String key = Normalizer.normalize(text, Normalizer.Form.NFC).toLowerCase(Locale.ROOT);
        if (key.length() > MAX_NAME_LENGTH) {
            // 大小写折叠/组合字符可能比原串更长，归一化后仍需落在列宽内
            throw new ServiceException(422, "文件名归一化后超过长度上限（"
                    + MAX_NAME_LENGTH + " 字符）");
        }
        return key;
    }

    private BioUserFile newRow(String userId, String kind, String key, String display,
                               String refId) {
        return BioUserFile.of(userId, kind, key, display, refId,
                OffsetDateTime.now(ZoneOffset.UTC).toString());
    }

    private String trimmed(String name) {
        String text = name == null ? "" : name.trim();
        if (text.isEmpty()) {
            throw new ServiceException(422, "文件名不能为空");
        }
        if (text.length() > MAX_NAME_LENGTH) {
            throw new ServiceException(422, "文件名超过长度上限（" + MAX_NAME_LENGTH + " 字符）");
        }
        return text;
    }
}
