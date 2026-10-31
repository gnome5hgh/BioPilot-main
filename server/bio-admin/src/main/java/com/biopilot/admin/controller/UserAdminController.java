package com.biopilot.admin.controller;

import cn.dev33.satoken.annotation.SaCheckRole;
import com.biopilot.common.core.R;
import com.biopilot.system.domain.LoginLog;
import com.biopilot.system.mapper.LoginLogMapper;
import com.biopilot.system.service.SysUserService;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.biopilot.system.domain.SysUser;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 管理端接口（ADMIN 专属，@SaCheckRole 强制）：用户管理/会话总览/审计日志。 */
@RestController
@RequestMapping("/admin/api")
public class UserAdminController {

    private final SysUserService userService;
    private final LoginLogMapper loginLogMapper;
    private final JdbcTemplate jdbc;

    public UserAdminController(SysUserService userService, LoginLogMapper loginLogMapper,
                               JdbcTemplate jdbc) {
        this.userService = userService;
        this.loginLogMapper = loginLogMapper;
        this.jdbc = jdbc;
    }

    /** 用户列表（全量，管理视角）。 */
    @GetMapping("/users")
    @SaCheckRole("ADMIN")
    public R<List<SysUser>> users() {
        return R.ok(userService.list());
    }

    /** 更新用户（status/role/nickName 白名单字段）。 */
    @PostMapping("/users/{userId}")
    @SaCheckRole("ADMIN")
    public R<Void> updateUser(@PathVariable Long userId, @RequestBody Map<String, String> body) {
        SysUser u = new SysUser();
        u.setUserId(userId);
        if (body.containsKey("status")) {
            u.setStatus(body.get("status"));
        }
        if (body.containsKey("role")) {
            u.setRole(body.get("role"));
        }
        if (body.containsKey("nickName")) {
            u.setNickName(body.get("nickName"));
        }
        userService.updateById(u);
        return R.ok();
    }

    /** 重置密码（BCrypt 重新摘要）。 */
    @PostMapping("/users/{userId}/reset-password")
    @SaCheckRole("ADMIN")
    public R<Void> resetPassword(@PathVariable Long userId, @RequestBody Map<String, String> body) {
        userService.resetPassword(userId, body.get("password"));
        return R.ok();
    }

    /** 会话总览（跨用户元数据：不展示对话内容明文）。 */
    @GetMapping("/sessions")
    @SaCheckRole("ADMIN")
    public R<List<Map<String, Object>>> sessions() {
        return R.ok(jdbc.queryForList(
                "SELECT a.agent_id, a.user_id, a.name, a.created_at,"
                + " (SELECT COUNT(*) FROM messages m WHERE m.agent_id = a.agent_id) AS message_count"
                + " FROM agent_state a ORDER BY a.created_at DESC LIMIT 200"));
    }

    /** 审计日志（最近 200 条，倒序）。 */
    @GetMapping("/audit")
    @SaCheckRole("ADMIN")
    public R<List<LoginLog>> audit() {
        return R.ok(loginLogMapper.selectList(
                new LambdaQueryWrapper<LoginLog>().orderByDesc(LoginLog::getId).last("LIMIT 200")));
    }
}
