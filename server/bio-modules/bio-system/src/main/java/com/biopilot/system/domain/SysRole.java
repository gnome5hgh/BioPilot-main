package com.biopilot.system.domain;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;

/** sys_role 表实体：内置 ADMIN/USER 两档（菜单级权限按 D4 裁掉）。 */
@TableName("sys_role")
public class SysRole {

    @TableId
    private Long roleId;
    /** 角色键：ADMIN / USER。 */
    private String roleKey;
    private String roleName;
    private String remark;

    public Long getRoleId() {
        return roleId;
    }

    public void setRoleId(Long roleId) {
        this.roleId = roleId;
    }

    public String getRoleKey() {
        return roleKey;
    }

    public void setRoleKey(String roleKey) {
        this.roleKey = roleKey;
    }

    public String getRoleName() {
        return roleName;
    }

    public void setRoleName(String roleName) {
        this.roleName = roleName;
    }

    public String getRemark() {
        return remark;
    }

    public void setRemark(String remark) {
        this.remark = remark;
    }
}
