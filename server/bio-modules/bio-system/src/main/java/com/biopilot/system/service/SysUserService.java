package com.biopilot.system.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.system.domain.SysUser;
import com.biopilot.system.mapper.SysUserMapper;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;

/** 用户账号服务：注册 / 查询 / 密码校验（密码只存 BCrypt 摘要）。 */
@Service
public class SysUserService {

    private final SysUserMapper userMapper;
    private final BCryptPasswordEncoder encoder = new BCryptPasswordEncoder();

    public SysUserService(SysUserMapper userMapper) {
        this.userMapper = userMapper;
    }

    /** 注册：用户名唯一校验 + 摘要落库；默认 USER 角色。 */
    public SysUser register(String userName, String rawPassword, String nickName) {
        if (findByUserName(userName) != null) {
            throw new ServiceException("用户名已存在");
        }
        SysUser u = new SysUser();
        u.setUserName(userName);
        u.setPassword(encoder.encode(rawPassword));
        u.setNickName(nickName == null || nickName.isBlank() ? userName : nickName);
        u.setRole("USER");
        u.setStatus("0");
        u.setCreateTime(java.time.LocalDateTime.now());
        userMapper.insert(u);
        return u;
    }

    /** 按用户名查（登录用）；不存在返回 null。 */
    public SysUser findByUserName(String userName) {
        return userMapper.selectOne(new LambdaQueryWrapper<SysUser>()
                .eq(SysUser::getUserName, userName));
    }

    /** 全量用户列表（管理端用；管理视角可见全部账号元数据）。 */
    public java.util.List<SysUser> list() {
        return userMapper.selectList(null);
    }

    /** 更新用户白名单字段与密码重置（管理端用）。 */
    /** 物理删除账号（删户两阶段第二步；引擎侧数据清干净后才走到这里）。 */
    public void deleteById(Long userId) {
        userMapper.deleteById(userId);
    }

    public void updateById(SysUser u) {
        userMapper.updateById(u);
    }

    /** 重置密码：BCrypt 重新摘要（管理端动作）。 */
    public void resetPassword(long userId, String rawPassword) {
        SysUser u = new SysUser();
        u.setUserId(userId);
        u.setPassword(encoder.encode(rawPassword));
        userMapper.updateById(u);
    }

    /** 按 id 查用户（资料/登录态用）；不存在返回 null。 */
    public SysUser getById(long userId) {
        return userMapper.selectById(userId);
    }

    /** 密码校验（BCrypt 比对）。 */
    public boolean checkPassword(SysUser u, String rawPassword) {
        return encoder.matches(rawPassword, u.getPassword());
    }
}
