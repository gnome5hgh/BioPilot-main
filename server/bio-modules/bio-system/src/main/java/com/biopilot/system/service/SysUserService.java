package com.biopilot.system.service;

import com.biopilot.system.domain.SysUser;
import java.util.List;

/** 用户账号服务：注册、查询与密码校验（密码只存 BCrypt 摘要）。 */
public interface SysUserService {

    /** 注册：用户名唯一校验 + 摘要落库；默认 USER 角色。 */
    SysUser register(String userName, String rawPassword, String nickName);

    /** 按用户名查（登录用）；不存在返回 null。 */
    SysUser findByUserName(String userName);

    /** 全量用户列表（管理端用）。 */
    List<SysUser> list();

    /** 物理删除账号（删户两阶段第二步）。 */
    void deleteById(Long userId);

    /** 更新用户白名单字段。 */
    void updateById(SysUser u);

    /** 重置密码：BCrypt 重新摘要。 */
    void resetPassword(long userId, String rawPassword);

    /** 按 id 查用户；不存在返回 null。 */
    SysUser getById(long userId);

    /** 密码校验（BCrypt 比对）。 */
    boolean checkPassword(SysUser u, String rawPassword);
}
