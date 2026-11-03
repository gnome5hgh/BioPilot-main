package com.biopilot.skill.dto;

import java.util.List;

/** 准入预览结果：staging 句柄 + 包内发现的全部技能。 */
public record InspectResult(
        String stagingId,
        List<SkillInfo> skills) {
}
