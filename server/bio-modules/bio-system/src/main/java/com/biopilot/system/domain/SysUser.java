package com.biopilot.system.domain;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.fasterxml.jackson.annotation.JsonIgnore;
import java.time.LocalDateTime;

/** sys_user 表实体（用户账号；user_id 即全局隔离键，Python 侧同键）。 */
@TableName("sys_user")
public class SysUser {

    @TableId
    private Long userId;
    private String userName;
    /** BCrypt 摘要；明文永不落库；不随任何响应序列化出去。 */
    @JsonIgnore
    private String password;
    /** 昵称/显示名（学生实名或花名）。 */
    private String nickName;
    /** 归属角色键：ADMIN / USER（两档）。 */
    private String role;
    /** 状态：0=正常 1=停用（删除走两阶段流程：先标记，物理删除延后）。 */
    private String status;
    private LocalDateTime createTime;

    public Long getUserId() {
        return userId;
    }

    public void setUserId(Long userId) {
        this.userId = userId;
    }

    public String getUserName() {
        return userName;
    }

    public void setUserName(String userName) {
        this.userName = userName;
    }

    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }

    public String getNickName() {
        return nickName;
    }

    public void setNickName(String nickName) {
        this.nickName = nickName;
    }

    public String getRole() {
        return role;
    }

    public void setRole(String role) {
        this.role = role;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public LocalDateTime getCreateTime() {
        return createTime;
    }

    public void setCreateTime(LocalDateTime createTime) {
        this.createTime = createTime;
    }
}
