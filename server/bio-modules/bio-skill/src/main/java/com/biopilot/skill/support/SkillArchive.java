package com.biopilot.skill.support;

import com.biopilot.common.core.exception.ServiceException;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Comparator;
import java.util.List;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;
import org.springframework.stereotype.Component;

/**
 * 技能目录与 zip 的互转。
 *
 * <p>打包是确定性的（按相对路径排序、不含目录条目），同一份内容永远得到同一个
 * sha256——它既是 OSS 对象键的组成部分，也是引擎本地缓存的键。</p>
 */
@Component
public class SkillArchive {

    /**
     * 把一个技能目录的内容打成 zip（SKILL.md 位于包根）。
     *
     * @param dir 技能目录
     * @return zip 字节
     * @throws ServiceException 文件数/大小超限（422）
     */
    public byte[] zipDirContents(Path dir) {
        List<Path> files;
        try (var walk = Files.walk(dir)) {
            files = walk.filter(Files::isRegularFile)
                    .sorted(Comparator.comparing(p -> dir.relativize(p).toString()))
                    .toList();
        } catch (IOException e) {
            throw new ServiceException(422, "读取技能目录失败: " + e.getMessage());
        }
        if (files.size() > SkillFetcher.MAX_ENTRIES) {
            throw new ServiceException(422, "技能文件数超过上限 " + SkillFetcher.MAX_ENTRIES);
        }
        long total = 0;
        for (Path file : files) {
            try {
                total += Files.size(file);
            } catch (IOException e) {
                throw new ServiceException(422, "读取技能文件失败: " + e.getMessage());
            }
            if (total > SkillFetcher.MAX_BYTES) {
                throw new ServiceException(422, "技能包超过大小上限 50MB");
            }
        }
        var buffer = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(buffer)) {
            for (Path file : files) {
                zip.putNextEntry(new ZipEntry(dir.relativize(file).toString().replace('\\', '/')));
                Files.copy(file, zip);
                zip.closeEntry();
            }
        } catch (IOException e) {
            throw new ServiceException(422, "打包技能失败: " + e.getMessage());
        }
        return buffer.toByteArray();
    }

    /** 计算内容 sha256（十六进制小写）。 */
    public String sha256(byte[] data) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(data);
            var hex = new StringBuilder(digest.length * 2);
            for (byte b : digest) {
                hex.append(String.format("%02x", b));
            }
            return hex.toString();
        } catch (Exception e) {
            throw new IllegalStateException("SHA-256 计算失败", e);
        }
    }
}
