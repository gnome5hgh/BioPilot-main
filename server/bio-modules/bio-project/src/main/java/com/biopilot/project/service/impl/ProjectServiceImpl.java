package com.biopilot.project.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.biopilot.project.domain.BioProject;
import com.biopilot.project.mapper.BioProjectMapper;
import com.biopilot.project.service.ProjectService;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

/** 项目 CRUD（科研课题分组；计费组为原型字段保留 UI 无逻辑）。 */
@Service
public class ProjectServiceImpl implements ProjectService {

    private final BioProjectMapper projectMapper;
    private final JdbcTemplate jdbc;

    public ProjectServiceImpl(BioProjectMapper projectMapper, JdbcTemplate jdbc) {
        this.projectMapper = projectMapper;
        this.jdbc = jdbc;
    }

    @Override
    public BioProject create(String userId, BioProject body) {
        BioProject project = new BioProject();
        project.setProjectId(UUID.randomUUID().toString());
        project.setUserId(userId);
        project.setName(body.getName());
        project.setBillingGroup(body.getBillingGroup());
        project.setDescription(body.getDescription());
        project.setCreateTime(LocalDateTime.now());
        projectMapper.insert(project);
        return project;
    }

    @Override
    public List<BioProject> list(String userId) {
        return projectMapper.selectList(new LambdaQueryWrapper<BioProject>()
                .eq(BioProject::getUserId, userId)
                .orderByDesc(BioProject::getCreateTime));
    }

    @Override
    public BioProject update(String userId, String projectId, BioProject body) {
        BioProject project = projectMapper.selectOne(new LambdaQueryWrapper<BioProject>()
                .eq(BioProject::getProjectId, projectId)
                .eq(BioProject::getUserId, userId));
        if (project == null) {
            return null;
        }
        if (body.getName() != null && !body.getName().isBlank()) {
            project.setName(body.getName().trim());
        }
        if (body.getDescription() != null) {
            project.setDescription(body.getDescription());
        }
        projectMapper.updateById(project);
        return project;
    }

    @Override
    public void delete(String userId, String projectId) {
        projectMapper.delete(new LambdaQueryWrapper<BioProject>()
                .eq(BioProject::getProjectId, projectId)
                .eq(BioProject::getUserId, userId));
        // 会话行的 project_id 不会随项目删除自动消失；不清掉的话这些会话
        // 既不在任何项目下、也不进未分组列表，等于从界面上消失。
        jdbc.update("UPDATE bio_agent_state SET project_id = NULL"
                + " WHERE user_id = ? AND project_id = ?", userId, projectId);
    }
}
