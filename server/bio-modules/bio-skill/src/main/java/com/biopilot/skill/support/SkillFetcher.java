package com.biopilot.skill.support;

import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.common.net.UrlGuard;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.regex.Pattern;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import org.eclipse.jgit.api.Git;
import org.eclipse.jgit.api.CloneCommand;
import org.eclipse.jgit.lib.ObjectId;
import org.springframework.stereotype.Component;

/**
 * 安装源拉取与技能目录发现。
 *
 * <p>支持两类来源：git（JGit，纯 Java，运行镜像无需 git 二进制）与 zip 上传。
 * 所有解包动作都带压缩炸弹与路径穿越闸门；本地路径来源不对浏览器开放。</p>
 */
@Component
public class SkillFetcher {

    /** 原始包与解压后总量上限（与既有的归档闸门一致）。 */
    public static final long MAX_BYTES = 50L * 1024 * 1024;
    public static final int MAX_ENTRIES = 2000;

    private static final Pattern SHORTHAND = Pattern.compile("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$");

    /** git 拉取结果：工作目录 + 来源元数据（url/ref/精确 sha）。 */
    public record Fetched(Path root, String url, String ref, String sha) {
    }

    /**
     * 克隆 git 来源到工作目录。
     *
     * @param source 完整 URL 或 owner/repo 简写
     * @param ref    分支/标签；null 用默认 HEAD
     * @param workDir 本次 staging 的工作目录
     * @return 仓库目录与来源元数据
     * @throws ServiceException 来源不可识别或拉取失败（422）
     */
    public Fetched fetchGit(String source, String ref, Path workDir) {
        String url = normalizeGitUrl(source);
        Path repo = workDir.resolve("repo");
        try {
            Files.createDirectories(workDir);
            CloneCommand command = Git.cloneRepository()
                    .setURI(url)
                    .setDirectory(repo.toFile())
                    .setDepth(1);
            if (ref != null && !ref.isBlank()) {
                command.setBranch(ref.trim());
            }
            try (Git git = command.call()) {
                ObjectId head = git.getRepository().resolve("HEAD");
                String sha = head == null ? "" : head.getName();
                return new Fetched(repo, url, ref == null ? null : ref.trim(), sha);
            }
        } catch (Exception e) {
            throw new ServiceException(422, "拉取 git 来源失败: " + e.getMessage());
        }
    }

    /**
     * 解压上传的 zip 到工作目录（压缩炸弹 / 路径穿越闸门）。
     *
     * @param data    上传字节
     * @param workDir 本次 staging 的工作目录
     * @return 解压后的根目录
     * @throws ServiceException 压缩包非法或超限（422）
     */
    public Path extractZip(byte[] data, Path workDir) {
        if (data == null || data.length == 0) {
            throw new ServiceException(422, "上传文件为空");
        }
        if (data.length > MAX_BYTES) {
            throw new ServiceException(422, "压缩包超过大小上限 50MB");
        }
        Path root = workDir.resolve("src");
        Path normalizedRoot = root.toAbsolutePath().normalize();
        try {
            Files.createDirectories(root);
            int count = 0;
            long total = 0;
            try (ZipInputStream zip = new ZipInputStream(new ByteArrayInputStream(data))) {
                ZipEntry entry;
                byte[] buffer = new byte[8192];
                while ((entry = zip.getNextEntry()) != null) {
                    if (++count > MAX_ENTRIES) {
                        throw new ServiceException(422, "压缩包超过文件数上限 " + MAX_ENTRIES);
                    }
                    Path target = normalizedRoot.resolve(entry.getName()).normalize();
                    if (!target.startsWith(normalizedRoot)) {
                        throw new ServiceException(422, "压缩包路径越界: " + entry.getName());
                    }
                    if (entry.isDirectory()) {
                        Files.createDirectories(target);
                        continue;
                    }
                    Files.createDirectories(target.getParent());
                    try (var out = Files.newOutputStream(target)) {
                        int read;
                        while ((read = zip.read(buffer)) != -1) {
                            total += read;
                            if (total > MAX_BYTES) {
                                throw new ServiceException(422, "压缩包解压后超过大小上限 50MB");
                            }
                            out.write(buffer, 0, read);
                        }
                    }
                }
            }
            return root;
        } catch (ServiceException e) {
            throw e;
        } catch (IOException e) {
            throw new ServiceException(422, "解压失败: " + e.getMessage());
        }
    }

    /**
     * 发现技能目录：根目录本身或一级子目录（兼容单仓多 skill）。
     *
     * @param root 来源根目录
     * @return 含 SKILL.md 的目录列表（按路径排序）
     */
    public List<Path> discoverSkillDirs(Path root) {
        if (!Files.isDirectory(root)) {
            return List.of();
        }
        if (Files.isRegularFile(root.resolve("SKILL.md"))) {
            return List.of(root);
        }
        List<Path> dirs = new ArrayList<>();
        try (var children = Files.list(root)) {
            children.filter(Files::isDirectory)
                    .filter(p -> Files.isRegularFile(p.resolve("SKILL.md")))
                    .sorted(Comparator.comparing(Path::toString))
                    .forEach(dirs::add);
        } catch (IOException e) {
            throw new ServiceException(422, "读取来源目录失败: " + e.getMessage());
        }
        return dirs;
    }

    /** 归一化 git 来源：owner/repo 简写补全为 GitHub；只接受 http(s)/ssh。 */
    private String normalizeGitUrl(String source) {
        String value = source == null ? "" : source.trim();
        if (value.isEmpty()) {
            throw new ServiceException(422, "安装源不能为空");
        }
        if (SHORTHAND.matcher(value).matches() && !value.contains("://")) {
            return "https://github.com/" + value + ".git";
        }
        if (value.startsWith("http://") || value.startsWith("https://")) {
            // 安装源由任意登录用户提交，是典型的 SSRF 入口：必须走公网校验，
            // 否则可以借它探测回环/内网/云元数据地址。
            try {
                UrlGuard.validateExternal(value);
            } catch (IllegalArgumentException e) {
                throw new ServiceException(422, "安装源不可访问: " + e.getMessage());
            }
            return value;
        }
        if (value.startsWith("ssh://") || value.startsWith("git@")) {
            return value;
        }
        throw new ServiceException(422, "无法识别的安装源（支持 git URL 或 owner/repo）: " + value);
    }

    /** 读取 zip 内的 SKILL.md 文本（详情展示用）。 */
    public static String readSkillMarkdown(byte[] zipBytes) {
        try (InputStream in = new ByteArrayInputStream(zipBytes);
             ZipInputStream zip = new ZipInputStream(in)) {
            ZipEntry entry;
            byte[] buffer = new byte[8192];
            while ((entry = zip.getNextEntry()) != null) {
                if (!entry.isDirectory() && "SKILL.md".equals(entry.getName())) {
                    var out = new java.io.ByteArrayOutputStream();
                    int read;
                    while ((read = zip.read(buffer)) != -1) {
                        out.write(buffer, 0, read);
                        if (out.size() > MAX_BYTES) {
                            throw new ServiceException(422, "SKILL.md 超过大小上限");
                        }
                    }
                    return out.toString(java.nio.charset.StandardCharsets.UTF_8);
                }
            }
        } catch (IOException e) {
            throw new ServiceException(422, "读取技能包失败: " + e.getMessage());
        }
        throw new ServiceException(422, "技能包内缺少 SKILL.md");
    }
}
