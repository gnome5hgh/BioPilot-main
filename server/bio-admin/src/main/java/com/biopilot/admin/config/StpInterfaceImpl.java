package com.biopilot.admin.config;

import cn.dev33.satoken.stp.StpInterface;
import com.biopilot.system.domain.SysUser;
import com.biopilot.system.service.SysUserService;
import java.util.List;
import org.springframework.stereotype.Component;

/** Sa-Token 角色数据源：把 sys_user.role 映射为角色列表（@SaCheckRole 的查询后端）。 */
@Component
public class StpInterfaceImpl implements StpInterface {

    private final SysUserService userService;

    public StpInterfaceImpl(SysUserService userService) {
        this.userService = userService;
    }

    @Override
    public List<String> getRoleList(Object loginId, String loginType) {
        SysUser u = userService.getById(Long.parseLong(loginId.toString()));
        if (u == null || u.getRole() == null) {
            return List.of();
        }
        return List.of(u.getRole());
    }

    @Override
    public List<String> getPermissionList(Object loginId, String loginType) {
        // 权限点未启用（两档角色按 role 判定即可）；需要细粒度权限时在此扩展
        return List.of();
    }
}
