package com.biopilot.skill.controller;

import com.biopilot.skill.service.SkillService;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 技能包内部入口：只给 Python 引擎取回「本人」的技能 zip 字节。
 *
 * <p>{@code /internal/**} 由 {@code InternalTokenFilter} 校验 token 与用户头；
 * 不存在与无权共用 404，避免泄露别人的技能是否存在。</p>
 */
@RestController
@RequestMapping("/internal/skills")
public class InternalSkillController {

    private final SkillService service;

    public InternalSkillController(SkillService service) {
        this.service = service;
    }

    @GetMapping("/{name}/package")
    public ResponseEntity<byte[]> packageFor(@PathVariable String name,
                                             @RequestHeader("X-User-Id") String userId) {
        SkillService.SkillPackage pkg = service.packageForUser(userId, name);
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType("application/zip"))
                .header("X-Content-Sha", pkg.sha())
                .body(pkg.data());
    }
}
