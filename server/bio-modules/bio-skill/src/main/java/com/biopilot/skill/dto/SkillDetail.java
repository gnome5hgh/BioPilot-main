package com.biopilot.skill.dto;

import java.util.List;

/** 技能详情：元数据 + SKILL.md 正文（页面详情抽屉用）。 */
public record SkillDetail(
        String name,
        String description,
        String version,
        String source,
        String sourceUrl,
        String sourceRef,
        boolean enabled,
        String installedAt,
        String content) {
}
