package com.biopilot.common.oss.config;

import io.minio.MinioClient;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** MinIO 客户端装配：连接参数来自 `biopilot.storage.minio`。 */
@Configuration
@EnableConfigurationProperties(MinioProperties.class)
public class MinioConfig {

    @Bean
    public MinioClient minioClient(MinioProperties properties) {
        // Java SDK 的 endpoint 必须是 URL；Python 侧配置沿用 host:port，这里补 scheme
        String endpoint = properties.getEndpoint();
        if (!endpoint.startsWith("http://") && !endpoint.startsWith("https://")) {
            endpoint = (properties.isSecure() ? "https://" : "http://") + endpoint;
        }
        return MinioClient.builder()
                .endpoint(endpoint)
                .credentials(properties.getAccessKey(), properties.getSecretKey())
                .build();
    }
}
