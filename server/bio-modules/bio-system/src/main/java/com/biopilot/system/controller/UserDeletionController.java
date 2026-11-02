package com.biopilot.system.controller;

import cn.dev33.satoken.annotation.SaCheckRole;
import cn.dev33.satoken.stp.StpUtil;
import com.biopilot.common.web.http.AgentInternalClient;
import com.biopilot.system.domain.SysUser;
import com.biopilot.system.service.PlatformUserDataService;
import com.biopilot.system.service.SysUserService;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.DeleteMapping;

/**
 * 删户两阶段（管理动作）：标记（停用登录 + 踢下线）与物理清理。
 *
 * <p>清理顺序：引擎数据（Python 经 /internal/users/*）→ 平台表行与 OSS 对象 →
 * 最后删账号。引擎侧失败时不删账号，管理员可重试，避免「账号没了、数据还在」。</p>
 */
@RestController
@RequestMapping("/api/v1/admin/users")
public class UserDeletionController {

    private static final String UNREACHABLE = "{\"code\":502,\"msg\":\"适配层不可达\"}";

    private final SysUserService users;
    private final PlatformUserDataService platformData;
    private final AgentInternalClient internal;

    public UserDeletionController(SysUserService users,
                                  PlatformUserDataService platformData,
                                  AgentInternalClient internal) {
        this.users = users;
        this.platformData = platformData;
        this.internal = internal;
    }

    /** 标记删除：引擎数据清理前先断掉该账号的会话与登录能力。 */
    @SaCheckRole("ADMIN")
    @PostMapping("/{targetId}/deletion")
    public ResponseEntity<String> markDeleting(@PathVariable String targetId) {
        try {
            StpUtil.kickout(Long.valueOf(targetId));
        } catch (Exception ignored) {
            // 目标本就不在线：kick 语义幂等
        }
        SysUser user = users.getById(Long.parseLong(targetId));
        if (user != null) {
            user.setStatus("1");
            users.updateById(user);
        }
        return forward("/internal/users/" + targetId + "/mark-deleting");
    }

    /** 物理清理：引擎侧成功后清平台数据与 OSS 对象，最后删账号。 */
    @SaCheckRole("ADMIN")
    @DeleteMapping("/{targetId}")
    public ResponseEntity<String> purge(@PathVariable String targetId) {
        ResponseEntity<String> upstream = forward("/internal/users/" + targetId + "/purge");
        if (upstream.getStatusCode().is2xxSuccessful()) {
            platformData.purge(targetId);
            SysUser user = users.getById(Long.parseLong(targetId));
            if (user != null) {
                users.deleteById(Long.parseLong(targetId));
            }
        }
        return upstream;
    }

    private ResponseEntity<String> forward(String path) {
        AgentInternalClient.InternalResponse resp =
                internal.postSync(path, StpUtil.getLoginIdAsLong(), Map.of());
        if (resp == null) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(UNREACHABLE);
        }
        return ResponseEntity.status(resp.status())
                .contentType(MediaType.APPLICATION_JSON)
                .body(resp.body());
    }
}
