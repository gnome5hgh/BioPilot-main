package com.biopilot.kb.controller;

import cn.dev33.satoken.stp.StpUtil;
import com.biopilot.kb.service.KbOverviewService;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 知识库概览：统计来自平台表，运行时信息由服务层向引擎取（不可达时降级）。 */
@RestController
@RequestMapping("/api/v1/kb")
public class KbOverviewController {

    private final KbOverviewService overview;

    public KbOverviewController(KbOverviewService overview) {
        this.overview = overview;
    }

    @GetMapping("/status")
    public Map<String, Object> status() {
        return overview.snapshot(StpUtil.getLoginIdAsLong());
    }
}
