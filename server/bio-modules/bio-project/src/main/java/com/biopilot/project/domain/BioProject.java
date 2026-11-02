package com.biopilot.project.domain;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import java.time.LocalDateTime;

/** bio_project 表实体（项目：科研课题分组；行级 user_id 由租户插件注入）。 */
@TableName("bio_project")
public class BioProject {

    @TableId
    private String projectId;
    /** 归属用户（租户列：MyBatis-Plus 拦截器自动注入查询条件）。 */
    private String userId;
    private String name;
    /** 计费组：genpilot 原型字段，保留 UI 无计费逻辑。 */
    private String billingGroup;
    private String description;
    private LocalDateTime createTime;

    public String getProjectId() {
        return projectId;
    }

    public void setProjectId(String projectId) {
        this.projectId = projectId;
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

    public String getBillingGroup() {
        return billingGroup;
    }

    public void setBillingGroup(String billingGroup) {
        this.billingGroup = billingGroup;
    }

    public String getDescription() {
        return description;
    }

    public void setDescription(String description) {
        this.description = description;
    }

    public LocalDateTime getCreateTime() {
        return createTime;
    }

    public void setCreateTime(LocalDateTime createTime) {
        this.createTime = createTime;
    }
}
