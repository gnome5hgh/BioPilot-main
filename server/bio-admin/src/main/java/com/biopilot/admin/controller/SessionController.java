package com.biopilot.admin.controller;

import com.biopilot.common.core.R;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 任务查询（读侧）：本用户的会话列表（含标题/消息数/预览），可按项目过滤。 */
@RestController
@RequestMapping("/sessions")
public class SessionController {

    private final JdbcTemplate jdbc;

    public SessionController(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** 会话列表（新→旧）：agent_state 行级隔离由租户插件注入（登录态 user_id）。 */
    @GetMapping
    public R<List<Map<String, Object>>> list(
            @RequestParam(required = false) String projectId,
            @RequestParam(defaultValue = "50") int limit) {
        String userId = StpUserId();
        String sql = ("SELECT a.agent_id, a.name, a.created_at, a.project_id,"
                + " (SELECT COUNT(*) FROM messages m WHERE m.agent_id = a.agent_id) AS message_count"
                + " FROM agent_state a WHERE a.user_id = ?")
                + (projectId != null && !projectId.isBlank() ? " AND a.project_id = ?" : "")
                + " ORDER BY a.created_at DESC LIMIT ?";
        var params = new java.util.ArrayList<Object>();
        params.add(userId);
        if (projectId != null && !projectId.isBlank()) {
            params.add(projectId);
        }
        params.add(limit);
        return R.ok(jdbc.queryForList(sql, params.toArray()));
    }

    private String StpUserId() {
        return cn.dev33.satoken.stp.StpUtil.getLoginIdAsString();
    }
}
