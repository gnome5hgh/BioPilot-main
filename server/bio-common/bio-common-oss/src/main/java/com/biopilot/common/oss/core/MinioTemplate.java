package com.biopilot.common.oss.core;

import com.biopilot.common.oss.config.MinioProperties;
import io.minio.BucketExistsArgs;
import io.minio.GetObjectArgs;
import io.minio.ListObjectsArgs;
import io.minio.MakeBucketArgs;
import io.minio.MinioClient;
import io.minio.PutObjectArgs;
import io.minio.RemoveObjectArgs;
import io.minio.Result;
import io.minio.errors.ErrorResponseException;
import io.minio.messages.Item;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import org.springframework.stereotype.Component;

/** MinIO 对象存取的最小封装：对象键与 Python 侧保持同一约定。 */
@Component
public class MinioTemplate {

    /** 单次读取上限：与上传上限（200MB）对齐，防止并发大对象把堆打爆。 */
    private static final long MAX_READ_BYTES = 256L * 1024 * 1024;

    /** 前缀批量删除的单次列举上限（删户清理用，超出部分留给下一轮对账）。 */
    private static final int MAX_PREFIX_OBJECTS = 10_000;

    private final MinioClient client;
    private final MinioProperties properties;

    public MinioTemplate(MinioClient client, MinioProperties properties) {
        this.client = client;
        this.properties = properties;
    }

    /** 写入字节对象；bucket 不存在时自动创建。 */
    public void putObject(String key, byte[] data, String contentType) {
        try {
            ensureBucket();
            client.putObject(PutObjectArgs.builder()
                    .bucket(properties.getBucket())
                    .object(key)
                    .stream(new ByteArrayInputStream(data), data.length, -1)
                    .contentType(contentType == null ? "application/octet-stream" : contentType)
                    .build());
        } catch (Exception e) {
            throw new IllegalStateException("MinIO 写入失败: " + key, e);
        }
    }

    /**
     * 读取对象；不存在或存储不可用时抛 IllegalStateException。
     *
     * <p>流式读取并卡上限：{@code readAllBytes()} 没有大小约束，几个并发大 PDF
     * 就能把整个平台进程的堆吃穿。</p>
     */
    public byte[] getObject(String key) {
        try (InputStream stream = client.getObject(GetObjectArgs.builder()
                .bucket(properties.getBucket())
                .object(key)
                .build())) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buffer = new byte[8192];
            long total = 0;
            int n;
            while ((n = stream.read(buffer)) != -1) {
                total += n;
                if (total > MAX_READ_BYTES) {
                    throw new IllegalStateException(
                            "MinIO 对象超过读取上限 " + MAX_READ_BYTES + " 字节: " + key);
                }
                out.write(buffer, 0, n);
            }
            return out.toByteArray();
        } catch (IllegalStateException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalStateException("MinIO 读取失败: " + key, e);
        }
    }

    /** 删除对象；对象或 bucket 不存在都视为成功（幂等）。 */
    public void removeObject(String key) {
        try {
            client.removeObject(RemoveObjectArgs.builder()
                    .bucket(properties.getBucket())
                    .object(key)
                    .build());
        } catch (ErrorResponseException e) {
            if (isNoSuchBucket(e)) {
                return;     // bucket 都没了，对象自然也不存在
            }
            throw new IllegalStateException("MinIO 删除失败: " + key, e);
        } catch (Exception e) {
            throw new IllegalStateException("MinIO 删除失败: " + key, e);
        }
    }

    /**
     * 按前缀删除对象（删户清理用）；失败只记在返回值里，不影响调用方继续清理。
     *
     * @param prefix 对象键前缀，如 {@code users/42/}
     * @return 实际尝试删除的对象数
     */
    public int removePrefix(String prefix) {
        int count = 0;
        try {
            Iterable<Result<Item>> items = client.listObjects(ListObjectsArgs.builder()
                    .bucket(properties.getBucket())
                    .prefix(prefix)
                    .recursive(true)
                    .maxKeys(1000)
                    .build());
            for (Result<Item> result : items) {
                if (count >= MAX_PREFIX_OBJECTS) {
                    break;
                }
                removeObject(result.get().objectName());
                count++;
            }
        } catch (ErrorResponseException e) {
            if (!isNoSuchBucket(e)) {
                throw new IllegalStateException("MinIO 前缀清理失败: " + prefix, e);
            }
        } catch (Exception e) {
            throw new IllegalStateException("MinIO 前缀清理失败: " + prefix, e);
        }
        return count;
    }

    private static boolean isNoSuchBucket(ErrorResponseException e) {
        return e.errorResponse() != null && "NoSuchBucket".equals(e.errorResponse().code());
    }

    private void ensureBucket() throws Exception {
        if (!client.bucketExists(BucketExistsArgs.builder()
                .bucket(properties.getBucket()).build())) {
            try {
                client.makeBucket(MakeBucketArgs.builder()
                        .bucket(properties.getBucket()).build());
            } catch (Exception e) {
                // 并发首启：另一个线程刚建好 bucket，这里再确认一次即可
                if (!client.bucketExists(BucketExistsArgs.builder()
                        .bucket(properties.getBucket()).build())) {
                    throw e;
                }
            }
        }
    }
}
