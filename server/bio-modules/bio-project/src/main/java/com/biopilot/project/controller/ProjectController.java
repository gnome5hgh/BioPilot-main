package com.biopilot.project.controller;

import cn.dev33.satoken.stp.StpUtil;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.biopilot.common.core.R;
import com.biopilot.project.domain.BioProject;
import com.biopilot.project.mapper.BioProjectMapper;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 项目 CRUD（科研课题分组；计费组为原型字段保留 UI 无逻辑）。 */
@RestController
@RequestMapping("/project")
public class ProjectController {

    private final BioProjectMapper projectMapper;
    private final JdbcTemplate jdbc;

    public ProjectController(BioProjectMapper projectMapper, JdbcTemplate jdbc) {
        this.projectMapper = projectMapper;
        this.jdbc = jdbc;
    }

    /** 新建项目（名称/计费组/简介；user_id 由租户插件注入）。 */
    @PostMapping
    public R<BioProject> create(@RequestBody BioProject body) {
        BioProject p = new BioProject();
        p.setProjectId(UUID.randomUUID().toString());
        p.setUserId(StpUtil.getLoginIdAsString());
        p.setName(body.getName());
        p.setBillingGroup(body.getBillingGroup());
        p.setDescription(body.getDescription());
        p.setCreateTime(LocalDateTime.now());
        projectMapper.insert(p);
        return R.ok(p);
    }

    /** 项目列表（本用户的，新→旧）。 */
    @GetMapping
    public R<List<BioProject>> list() {
        String userId = StpUtil.getLoginIdAsString();
        List<BioProject> rows = projectMapper.selectList(
                new LambdaQueryWrapper<BioProject>()
                        .eq(BioProject::getUserId, userId)
                        .orderByDesc(BioProject::getCreateTime));
        return R.ok(rows);
    }

    /** 重命名/改简介（只动当前用户的这一行；空名不覆盖）。 */
    @PutMapping("/{projectId}")
    public R<BioProject> update(@PathVariable String projectId,
                                @RequestBody BioProject body) {
        String userId = StpUtil.getLoginIdAsString();
        BioProject p = projectMapper.selectOne(new LambdaQueryWrapper<BioProject>()
                .eq(BioProject::getProjectId, projectId)
                .eq(BioProject::getUserId, userId));
        if (p == null) {
            return R.fail("项目不存在");
        }
        if (body.getName() != null && !body.getName().isBlank()) {
            p.setName(body.getName().trim());
        }
        if (body.getDescription() != null) {
            p.setDescription(body.getDescription());
        }
        projectMapper.updateById(p);
        return R.ok(p);
    }

    /** 删除项目（会话不级联删——它们退回未分组）。 */
    @DeleteMapping("/{projectId}")
    public R<Void> delete(@PathVariable String projectId) {
        String userId = StpUtil.getLoginIdAsString();
        projectMapper.delete(new LambdaQueryWrapper<BioProject>()
                .eq(BioProject::getProjectId, projectId)
                .eq(BioProject::getUserId, userId));
        // 会话行的 project_id 不会随项目删除自动消失；不清掉的话这些会话
        // 既不在任何项目下、也不进未分组列表，等于从界面上消失。
        jdbc.update("UPDATE bio_agent_state SET project_id = NULL"
                + " WHERE user_id = ? AND project_id = ?", userId, projectId);
        return R.ok();
    }
}
