package com.biopilot.file.domain;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

/**
 * bio_user_file 行：用户文件名的唯一登记。
 *
 * <p>论文 / 数据文件 / 文档共用一个名字空间；唯一键 {@code (user_id, name_key)}
 * 是权威约束，应用层不再逐表扫描查重。分析产物不登记（可跨 run 重名）。</p>
 */
@TableName("bio_user_file")
public class BioUserFile {

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;
    private String userId;
    private String kind;
    private String nameKey;
    private String name;
    private String refId;
    private String createdAt;

    /** 构造一行待登记记录（id 由数据库自增）。 */
    public static BioUserFile of(String userId, String kind, String nameKey, String name,
                                 String refId, String createdAt) {
        BioUserFile row = new BioUserFile();
        row.setUserId(userId);
        row.setKind(kind);
        row.setNameKey(nameKey);
        row.setName(name);
        row.setRefId(refId);
        row.setCreatedAt(createdAt);
        return row;
    }

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

    public String getKind() {
        return kind;
    }

    public void setKind(String kind) {
        this.kind = kind;
    }

    public String getNameKey() {
        return nameKey;
    }

    public void setNameKey(String nameKey) {
        this.nameKey = nameKey;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getRefId() {
        return refId;
    }

    public void setRefId(String refId) {
        this.refId = refId;
    }

    public String getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(String createdAt) {
        this.createdAt = createdAt;
    }
}
