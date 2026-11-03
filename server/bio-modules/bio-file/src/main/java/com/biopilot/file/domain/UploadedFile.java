package com.biopilot.file.domain;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

/** bio_file_upload 行：对话附件/数据文件元数据。 */
@TableName("bio_file_upload")
public class UploadedFile {

    /** 用户上传：参与同名约束。 */
    public static final String SOURCE_UPLOAD = "upload";
    /** agent 分析产物：跨 run 重名是正常现象，不参与同名约束。 */
    public static final String SOURCE_ARTIFACT = "artifact";

    @TableId(type = IdType.INPUT)
    private String id;
    private String userId;
    private String name;
    private String ossKey;
    private Long sizeBytes;
    private String contentType;
    /** 来源：upload=用户上传（参与同名约束）/ artifact=分析产物（可重名）。 */
    private String source;
    private String createdAt;

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getUserId() {
        return userId;
    }

    public void setUserId(String userId) {
        this.userId = userId;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getOssKey() {
        return ossKey;
    }

    public void setOssKey(String ossKey) {
        this.ossKey = ossKey;
    }

    public Long getSizeBytes() {
        return sizeBytes;
    }

    public void setSizeBytes(Long sizeBytes) {
        this.sizeBytes = sizeBytes;
    }

    public String getContentType() {
        return contentType;
    }

    public void setContentType(String contentType) {
        this.contentType = contentType;
    }

    public String getSource() {
        return source;
    }

    public void setSource(String source) {
        this.source = source;
    }

    public String getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(String createdAt) {
        this.createdAt = createdAt;
    }
}
