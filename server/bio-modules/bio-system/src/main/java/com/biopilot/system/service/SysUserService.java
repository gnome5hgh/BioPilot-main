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

    /** 密码校验（BCrypt 比对）。 */
    public boolean checkPassword(SysUser u, String rawPassword) {
        return encoder.matches(rawPassword, u.getPassword());
    }
}
