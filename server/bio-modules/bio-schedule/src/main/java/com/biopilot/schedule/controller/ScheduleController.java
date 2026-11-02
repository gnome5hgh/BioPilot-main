package com.biopilot.schedule.controller;

import cn.dev33.satoken.stp.StpUtil;
import com.biopilot.schedule.dto.ScheduleView;
import com.biopilot.schedule.service.ScheduleService;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 定时任务定义 CRUD（执行由 Python 引擎的调度循环消费）。 */
@RestController
@RequestMapping("/agent/schedules")
public class ScheduleController {

    private final ScheduleService service;

    public ScheduleController(ScheduleService service) {
        this.service = service;
    }

    @GetMapping
    public Map<String, Object> list() {
        List<ScheduleView> rows = service.list();
        return Map.of("schedules", rows);
    }

    @PostMapping
    public Map<String, Object> create(@RequestBody Map<String, Object> body) {
        return service.create(StpUtil.getLoginIdAsString(), body);
    }

    @PostMapping("/{taskId}/pause")
    public Map<String, Object> pause(@PathVariable String taskId) {
        return service.setPaused(taskId, 1);
    }

    @PostMapping("/{taskId}/resume")
    public Map<String, Object> resume(@PathVariable String taskId) {
        return service.setPaused(taskId, 0);
    }

    @PostMapping("/{taskId}/run")
    public Map<String, Object> runNow(@PathVariable String taskId) {
        return service.runNow(taskId);
    }

    @DeleteMapping("/{taskId}")
    public Map<String, Object> delete(@PathVariable String taskId) {
        return service.delete(taskId);
    }
}
