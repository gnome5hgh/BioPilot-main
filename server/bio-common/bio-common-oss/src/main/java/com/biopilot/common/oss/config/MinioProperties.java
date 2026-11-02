package com.biopilot.common.oss.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/** MinIO 连接配置（与 Python 侧 rag.storage.minio 同一实例/同一 bucket）。 */
@ConfigurationProperties(prefix = "biopilot.storage.minio")
public class MinioProperties {

    /** MinIO 地址，host:port（不带 scheme）。 */
    private String endpoint = "localhost:9000";
    private String accessKey = "minioadmin";
    private String secretKey = "minioadmin";
    /** 存放论文/用户文件/图表原图的 bucket。 */
    private String bucket = "biopilot-images";
    private boolean secure = false;

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    public String getAccessKey() {
        return accessKey;
    }

    public void setAccessKey(String accessKey) {
        this.accessKey = accessKey;
    }

    public String getSecretKey() {
        return secretKey;
    }

    public void setSecretKey(String secretKey) {
        this.secretKey = secretKey;
    }

    public String getBucket() {
        return bucket;
    }

    public void setBucket(String bucket) {
        this.bucket = bucket;
    }

    public boolean isSecure() {
        return secure;
    }

    public void setSecure(boolean secure) {
        this.secure = secure;
    }
}
