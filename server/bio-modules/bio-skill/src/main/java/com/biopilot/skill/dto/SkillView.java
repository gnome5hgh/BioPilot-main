package com.biopilot.skill.dto;

import java.util.List;

/** 技能的对外视图（列表/安装/启停/更新共用）。 */
public record SkillView(
        String name,
        String description,
        String version,
        String source,
        String sourceUrl,
        String sourceRef,
        boolean enabled,
        String installedAt) {
}
