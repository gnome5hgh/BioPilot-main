package com.biopilot.literature.controller;

import cn.dev33.satoken.stp.StpUtil;
import com.biopilot.literature.service.LiteratureImportService;
import com.biopilot.literature.service.LiteratureSearchService;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 文献搜索与导入（路径与响应结构保持前端既有契约）。 */
@RestController
@RequestMapping("/api/v1/literature")
public class LiteratureController {

    private final LiteratureSearchService searchService;
    private final LiteratureImportService importService;

    public LiteratureController(LiteratureSearchService searchService,
                                LiteratureImportService importService) {
        this.searchService = searchService;
        this.importService = importService;
    }

    @GetMapping("/search")
    public Map<String, Object> search(@RequestParam(defaultValue = "") String q) {
        return searchService.search(q);
    }

    @PostMapping("/import")
    public Map<String, Object> importPaper(@RequestBody Map<String, Object> body) {
        return importService.importPaper(StpUtil.getLoginIdAsLong(), body);
    }
}
