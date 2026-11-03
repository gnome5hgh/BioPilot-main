package com.biopilot.skill.support;

import com.biopilot.common.core.exception.ServiceException;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.Comparator;
import java.util.UUID;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import org.springframework.stereotype.Component;

/**
 * 安装预览的临时工作区（Java 容器本地临时目录，不落 OSS、不需要共享卷）。
 *
 * <p>inspect 把来源拉进 staging，install 从 staging 落库后删除；未确认的 staging
 * 由每次 inspect 时的 TTL 清理回收。目录按用户分域，install 只接受同一用户的句柄。</p>
 */
@Component
public class SkillStaging {

    private static final Path ROOT =
            Path.of(System.getProperty("java.io.tmpdir"), "biopilot-skill-staging");
    private static final Pattern UUID_PATTERN =
            Pattern.compile("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$");
    private static final Duration MAX_AGE = Duration.ofHours(2);

    /**
     * 创建一次 staging 并回收过期目录。
     *
     * @param userId 归属用户
     * @return staging 句柄（UUID）
     */
    public String create(long userId) {
        cleanupExpired();
        String id = UUID.randomUUID().toString();
        try {
            Files.createDirectories(dir(userId, id));
        } catch (IOException e) {
            throw new IllegalStateException("创建技能暂存目录失败", e);
        }
        return id;
    }

    /**
     * 解析用户私有 staging 目录。
     *
     * @param userId 归属用户
     * @param id     句柄
     * @return staging 根目录（含 src/）
     * @throws ServiceException 句柄非法或不属于该用户（422）
     */
    public Path dir(long userId, String id) {
        if (id == null || !UUID_PATTERN.matcher(id).matches()) {
            throw new ServiceException(422, "安装会话标识非法");
        }
        return ROOT.resolve(safe(userId)).resolve(id);
    }

    /** 删除 staging（安装成功后调用；不存在视为成功）。 */
    public void delete(long userId, String id) {
        deleteQuietly(ROOT.resolve(safe(userId)).resolve(id));
    }

    /** 回收超过 TTL 的 staging（每次 create 时顺带执行）。 */
    public void cleanupExpired() {
        if (!Files.isDirectory(ROOT)) {
            return;
        }
        Instant cutoff = Instant.now().minus(MAX_AGE);
        try (Stream<Path> users = Files.list(ROOT)) {
            users.filter(Files::isDirectory).forEach(userDir -> {
                try (Stream<Path> sessions = Files.list(userDir)) {
                    sessions.filter(Files::isDirectory).forEach(dir -> {
                        try {
                            if (Files.getLastModifiedTime(dir).toInstant().isBefore(cutoff)) {
                                deleteQuietly(dir);
                            }
                        } catch (IOException ignored) {
                            // 清理是尽力而为：单个目录读失败不影响安装
                        }
                    });
                } catch (IOException ignored) {
                    // 同上
                }
            });
        } catch (IOException ignored) {
            // 同上
        }
    }

    private void deleteQuietly(Path dir) {
        if (!Files.exists(dir)) {
            return;
        }
        try (Stream<Path> walk = Files.walk(dir)) {
            walk.sorted(Comparator.reverseOrder()).forEach(p -> {
                try {
                    Files.deleteIfExists(p);
                } catch (IOException ignored) {
                    // 尽力清理
                }
            });
        } catch (IOException ignored) {
            // 尽力清理
        }
    }

    private String safe(long userId) {
        return ("u" + userId).replaceAll("[^A-Za-z0-9_-]", "_");
    }
}
