package com.biopilot.system.controller;

import cn.dev33.satoken.stp.StpUtil;
import com.biopilot.common.core.R;
import com.biopilot.system.domain.LoginLog;
import com.biopilot.system.domain.SysUser;
import com.biopilot.system.mapper.LoginLogMapper;
import com.biopilot.system.service.SysUserService;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/** 认证接口：注册 / 登录 / 登出 / 当前用户资料。 */
@RestController
public class AuthController {

    private final SysUserService userService;
    private final LoginLogMapper loginLogMapper;

    public AuthController(SysUserService userService, LoginLogMapper loginLogMapper) {
        this.userService = userService;
        this.loginLogMapper = loginLogMapper;
    }

    /** 注册：默认 USER 角色；用户名冲突返回失败。 */
    @PostMapping("/api/v1/auth/register")
    public R<SysUser> register(@RequestBody Map<String, String> body) {
        SysUser u = userService.register(
                body.get("userName"), body.get("password"), body.get("nickName"));
        return R.ok(u);
    }

    /** 登录：BCrypt 校验 + Sa-Token 会话；成败都记登录日志。 */
    @PostMapping("/api/v1/auth/login")
    public R<Map<String, Object>> login(@RequestBody Map<String, String> body,
                                        HttpServletRequest request) {
        String userName = body.get("userName");
        String password = body.get("password");
        SysUser u = userService.findByUserName(userName);
        if (u == null || !userService.checkPassword(u, password)) {
            recordLogin(userName, u == null ? null : u.getUserId(), "failed", request);
            return R.fail("用户名或密码错误");
        }
        if ("1".equals(u.getStatus())) {
            recordLogin(userName, u.getUserId(), "failed", request);
            return R.fail("账号已停用");
        }
        StpUtil.login(u.getUserId());
        recordLogin(userName, u.getUserId(), "success", request);
        return R.ok(Map.of(
                "token", StpUtil.getTokenValue(),
                "userId", u.getUserId(),
                "role", u.getRole(),
                "nickName", u.getNickName() == null ? "" : u.getNickName()));
    }

    /** 登出：结束当前会话。 */
    @PostMapping("/api/v1/auth/logout")
    public R<Void> logout() {
        StpUtil.logout();
        return R.ok();
    }

    /** 当前登录用户资料。 */
    @GetMapping("/api/v1/users/me")
    public R<SysUser> profile() {
        long userId = StpUtil.getLoginIdAsLong();
        return R.ok(userService.getById(userId));
    }

    private void recordLogin(String userName, Long userId, String outcome,
                             HttpServletRequest request) {
        LoginLog log = new LoginLog();
        log.setUserName(userName);
        log.setUserId(userId);
        log.setOutcome(outcome);
        log.setIp(request.getRemoteAddr());
        log.setCreateTime(java.time.LocalDateTime.now());
        loginLogMapper.insert(log);
    }
}
