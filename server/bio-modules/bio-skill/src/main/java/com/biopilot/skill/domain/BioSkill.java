package com.biopilot.skill.domain;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

/** bio_skill 行：一个用户安装的一个技能包（内容本体在 OSS，表只存元数据）。 */
@TableName("bio_skill")
public class BioSkill {

    @TableId(type = IdType.AUTO)
    private Long id;
    private String userId;
    private String name;
    private String description;
    private String version;
    /** 来源类型：git / archive。 */
    private String source;
    private String sourceUrl;
    private String sourceRef;
    private String sourceSha;
    /** OSS 对象键：users/<uid>/skills/<name>/<content_sha>.zip。 */
    private String ossKey;
    /** zip 内容 sha256：引擎本地缓存的键，也是对象不可变性的锚点。 */
    private String contentSha;
    private Integer enabled;
    private String installedAt;

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
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

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public String getVersion() {
        return version;
    }

    public void setVersion(String version) {
        this.version = version;
    }

    public String getSource() {
        return source;
    }

    public void setSource(String source) {
        this.source = source;
    }

    public String getSourceUrl() {
        return sourceUrl;
    }

    public void setSourceUrl(String sourceUrl) {
        this.sourceUrl = sourceUrl;
    }

    public String getSourceRef() {
        return sourceRef;
    }

    public void setSourceRef(String sourceRef) {
        this.sourceRef = sourceRef;
    }

    public String getSourceSha() {
        return sourceSha;
    }

    public void setSourceSha(String sourceSha) {
        this.sourceSha = sourceSha;
    }

    public String getOssKey() {
        return ossKey;
    }

    public void setOssKey(String ossKey) {
        this.ossKey = ossKey;
    }

    public String getContentSha() {
        return contentSha;
    }

    public void setContentSha(String contentSha) {
        this.contentSha = contentSha;
    }

    public Integer getEnabled() {
        return enabled;
    }

    public void setEnabled(Integer enabled) {
        this.enabled = enabled;
    }

    public String getInstalledAt() {
        return installedAt;
    }

    public void setInstalledAt(String installedAt) {
        this.installedAt = installedAt;
    }
}
