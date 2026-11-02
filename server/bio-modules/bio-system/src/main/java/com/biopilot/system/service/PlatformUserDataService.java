package com.biopilot.system.service;

/** 平台用户数据清理：删户流程的 Java 半边。 */
public interface PlatformUserDataService {

    /**
     * 清理该用户的全部平台数据（幂等）。
     *
     * Args:
     *     userId: 目标用户（sys_user.user_id 的字符串形式）。
     */
    void purge(String userId);
}
