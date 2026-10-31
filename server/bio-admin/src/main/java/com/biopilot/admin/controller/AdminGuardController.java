package com.biopilot.admin.controller;

import cn.dev33.satoken.annotation.SaCheckRole;
import com.biopilot.common.core.R;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 管理端守卫锚点：验证两档角色的接口层隔离（USER 调用即 403）。

    完整管理面（用户管理/总览/审计）在工单 24 展开，本控制器只承担
    「角色注解生效」的可测性。
*/
@RestController
@RequestMapping("/admin/api")
public class AdminGuardController {

    @GetMapping("/roles")
    @SaCheckRole("ADMIN")
    public R<List<String>> roles() {
        return R.ok(List.of("ADMIN", "USER"));
    }
}
