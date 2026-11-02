package com.biopilot.project.controller;

import cn.dev33.satoken.stp.StpUtil;
import com.biopilot.common.core.R;
import com.biopilot.project.domain.BioProject;
import com.biopilot.project.service.ProjectService;
import java.util.List;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.PatchMapping;

/** 项目 CRUD（科研课题分组；计费组为原型字段保留 UI 无逻辑）。 */
@RestController
@RequestMapping("/api/v1/projects")
public class ProjectController {

    private final ProjectService service;

    public ProjectController(ProjectService service) {
        this.service = service;
    }

    /** 新建项目（名称/计费组/简介；user_id 按登录态写入）。 */
    @PostMapping
    public R<BioProject> create(@RequestBody BioProject body) {
        return R.ok(service.create(uid(), body));
    }

    /** 项目列表（本用户的，新→旧）。 */
    @GetMapping
    public R<List<BioProject>> list() {
        return R.ok(service.list(uid()));
    }

    /** 重命名/改简介（只动当前用户的这一行；空名不覆盖）。 */
    @PatchMapping("/{projectId}")
    public R<BioProject> update(@PathVariable String projectId,
                                @RequestBody BioProject body) {
        BioProject project = service.update(uid(), projectId, body);
        return project == null ? R.fail("项目不存在") : R.ok(project);
    }

    /** 删除项目（会话不级联删——它们退回未分组）。 */
    @DeleteMapping("/{projectId}")
    public R<Void> delete(@PathVariable String projectId) {
        service.delete(uid(), projectId);
        return R.ok();
    }

    private String uid() {
        return StpUtil.getLoginIdAsString();
    }
}
