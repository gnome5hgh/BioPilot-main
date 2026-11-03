package com.biopilot.file.domain;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

/** OSS 删除 outbox 的一行：数据库提交后再删对象，失败由定时任务重试。 */
@TableName("bio_oss_gc")
public class BioOssGc {

    @TableId(type = IdType.AUTO)
    private Long id;
    private String ossKey;
    private String reason;
    private Integer attempts;
    private String nextAt;
    private String createdAt;

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getOssKey() {
        return ossKey;
    }

    public void setOssKey(String ossKey) {
        this.ossKey = ossKey;
    }

    public String getReason() {
        return reason;
    }

    public void setReason(String reason) {
        this.reason = reason;
    }

    public Integer getAttempts() {
        return attempts;
    }

    public void setAttempts(Integer attempts) {
        this.attempts = attempts;
    }

    public String getNextAt() {
        return nextAt;
    }

    public void setNextAt(String nextAt) {
        this.nextAt = nextAt;
    }

    public String getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(String createdAt) {
        this.createdAt = createdAt;
    }
}
