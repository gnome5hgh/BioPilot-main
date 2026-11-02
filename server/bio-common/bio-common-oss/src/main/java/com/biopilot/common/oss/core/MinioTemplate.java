package com.biopilot.common.oss.core;

import com.biopilot.common.oss.config.MinioProperties;
import io.minio.BucketExistsArgs;
import io.minio.GetObjectArgs;
import io.minio.MakeBucketArgs;
import io.minio.MinioClient;
import io.minio.PutObjectArgs;
import io.minio.RemoveObjectArgs;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import org.springframework.stereotype.Component;

/** MinIO 对象存取的最小封装：对象键与 Python 侧保持同一约定。 */
@Component
public class MinioTemplate {

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

    /** 读取对象；不存在或存储不可用时抛 IllegalStateException。 */
    public byte[] getObject(String key) {
        try (InputStream stream = client.getObject(GetObjectArgs.builder()
                .bucket(properties.getBucket())
                .object(key)
                .build())) {
            return stream.readAllBytes();
        } catch (Exception e) {
            throw new IllegalStateException("MinIO 读取失败: " + key, e);
        }
    }

    /** 删除对象；不存在也视为成功。 */
    public void removeObject(String key) {
        try {
            client.removeObject(RemoveObjectArgs.builder()
                    .bucket(properties.getBucket())
                    .object(key)
                    .build());
        } catch (Exception e) {
            throw new IllegalStateException("MinIO 删除失败: " + key, e);
        }
    }

    private void ensureBucket() throws Exception {
        if (!client.bucketExists(BucketExistsArgs.builder()
                .bucket(properties.getBucket()).build())) {
            client.makeBucket(MakeBucketArgs.builder()
                    .bucket(properties.getBucket()).build());
        }
    }
}
