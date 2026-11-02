package com.biopilot.project.service;

import com.biopilot.project.domain.BioProject;
import java.util.List;

/** 课题分组：项目 CRUD 与会话归属的维护。 */
public interface ProjectService {

    /** 新建项目（user_id 由服务层按登录态写入）。 */
    BioProject create(String userId, BioProject body);

    /** 本用户的全部项目（新→旧）。 */
    List<BioProject> list(String userId);

    /** 重命名/改简介；项目不存在或不属于本人时返回 null。 */
    BioProject update(String userId, String projectId, BioProject body);

    /** 删除项目；会话退回未分组（引擎表的唯一一处平台侧写）。 */
    void delete(String userId, String projectId);
}
