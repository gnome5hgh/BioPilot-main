package com.biopilot.file.service;

import com.biopilot.common.oss.core.MinioTemplate;
import com.biopilot.file.domain.BioOssGc;
import com.biopilot.file.mapper.BioFileMapper;
import com.biopilot.file.mapper.BioOssGcMapper;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * OSS 对象删除与孤儿对账。
 *
 * <p>写入协议是“对象先落、指针后改、提交后再删旧对象”；删除协议是“行先删、
 * 对象交给本服务”。所有删除都经这里，失败只留下没人引用的对象，绝不会出现
 * 指向不存在对象的行。</p>
 */
@Service
public class OssGcService {

    private static final Logger log = LoggerFactory.getLogger(OssGcService.class);

    /** 旧对象延迟删除的宽限期：让已经读到旧键的请求有时间完成读取。 */
    private static final long GRACE_SECONDS = 600L;

    /** 单次扫描上限，防止一次列举把进程内存打满。 */
    private static final int LIST_LIMIT = 10_000;

    private final BioOssGcMapper gcMapper;
    private final BioFileMapper fileMapper;
    private final MinioTemplate minio;

    public OssGcService(BioOssGcMapper gcMapper, BioFileMapper fileMapper,
                        MinioTemplate minio) {
        this.gcMapper = gcMapper;
        this.fileMapper = fileMapper;
        this.minio = minio;
    }

    /** 入队一个待删对象（宽限期后删除）。 */
    public void enqueue(String ossKey, String reason) {
        enqueue(ossKey, reason, GRACE_SECONDS);
    }

    /** 入队一个待删对象；delaySeconds=0 表示下一轮立即处理。 */
    public void enqueue(String ossKey, String reason, long delaySeconds) {
        if (ossKey == null || ossKey.isBlank()) {
            return;
        }
        String nextAt = OffsetDateTime.now(ZoneOffset.UTC)
                .plusSeconds(Math.max(0, delaySeconds)).toString();
        gcMapper.insertIgnore(ossKey, reason, nextAt, now());
    }

    /** 处理到期的删除任务；失败按指数退避重试。 */
    public void runDue() {
        List<BioOssGc> due = gcMapper.selectDue(now(), 200);
        for (BioOssGc row : due) {
            try {
                // 删除前复核引用：并发写入可能仍指向这个键（正常路径每次尝试键都不同，
                // 这里是对历史键/异常路径的兜底），有引用就只丢弃队列行。
                if (fileMapper.countByOssKey(row.getOssKey()) > 0) {
                    gcMapper.deleteById(row.getId());
                    continue;
                }
                minio.removeObject(row.getOssKey());
                gcMapper.deleteById(row.getId());
            } catch (RuntimeException e) {
                int attempts = row.getAttempts() == null ? 0 : row.getAttempts();
                int next = Math.min(3600, 30 << Math.min(attempts, 6));
                row.setAttempts(attempts + 1);
                row.setNextAt(OffsetDateTime.now(ZoneOffset.UTC)
                        .plusSeconds(next).toString());
                gcMapper.updateById(row);
                log.warn("OSS 删除失败，稍后重试 key={} attempts={}: {}",
                        row.getOssKey(), attempts + 1, e.getMessage());
            }
        }
    }

    /**
     * 对账一个用户的文件前缀：删除没有任何 {@code bio_file.oss_key} 引用的对象。
     *
     * <p>只扫 {@code users/<uid>/files/} 与 {@code users/<uid>/papers/}，
     * 不碰技能包、工具结果与 RAG 图表；旧版本对象因为不在当前指针集合里，
     * 会自然成为孤儿并在宽限期后被清理。</p>
     */
    public void reconcileUser(String userId) {
        Set<String> referenced = new HashSet<>(fileMapper.selectOssKeysForUser(userId));
        String safeUser = com.biopilot.file.domain.FileObjectKeys.safeSegment(userId);
        for (String prefix : List.of("users/" + safeUser + "/files/",
                "users/" + safeUser + "/papers/")) {
            for (MinioTemplate.ObjectInfo info : minio.listKeys(prefix, LIST_LIMIT)) {
                if (referenced.contains(info.key())) {
                    continue;
                }
                if (info.lastModified() != null
                        && info.lastModified().isAfter(
                                java.time.ZonedDateTime.now(ZoneOffset.UTC)
                                        .minusSeconds(GRACE_SECONDS))) {
                    continue;   // 刚写入、可能尚未提交的指针，留到下轮
                }
                enqueue(info.key(), "reconcile", 0);
            }
        }
    }

    /** 对所有用户做一轮前缀对账（定时任务调用）。 */
    public void reconcileAll() {
        for (String userId : fileMapper.selectDistinctUsers()) {
            try {
                reconcileUser(userId);
            } catch (RuntimeException e) {
                log.warn("用户 {} 的 OSS 对账失败，稍后重试: {}", userId, e.getMessage());
            }
        }
    }

    private String now() {
        return OffsetDateTime.now(ZoneOffset.UTC).toString();
    }
}
