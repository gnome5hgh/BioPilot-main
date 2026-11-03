package com.biopilot.skill.dto;

import java.util.List;

/** 一个技能包的解析结果（准入预览与安装共用）。 */
public record SkillInfo(
        String name,
        String description,
        String version,
        String license,
        List<String> resources) {
}
