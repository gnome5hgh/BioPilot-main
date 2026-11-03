package com.biopilot.skill.service;

import com.biopilot.skill.dto.InspectResult;
import com.biopilot.skill.dto.SkillDetail;
import com.biopilot.skill.dto.SkillView;
import java.util.List;

/** 用户技能管理：安装/启停/更新/卸载与内部取包。 */
public interface SkillService {

    /** 当前用户（租户插件注入）的全部技能。 */
    List<SkillView> list(long userId);

    /** 详情：元数据 + SKILL.md 正文。 */
    SkillDetail detail(long userId, String name);

    /** 预览 git 来源（无副作用，只落 staging）。 */
    InspectResult inspectGit(long userId, String source, String ref);

    /** 预览上传的 zip（无副作用，只落 staging）。 */
    InspectResult inspectZip(long userId, byte[] data);

    /** 从 staging 安装全部技能（对象先落、行后写）。 */
    List<SkillView> install(long userId, String stagingId);

    /** 启用/停用。 */
    SkillView toggle(long userId, String name, boolean enabled);

    /** 仅 git 来源：按记录地址重拉并原子替换。 */
    SkillView update(long userId, String name);

    /** 卸载：先删行、再删对象。 */
    void delete(long userId, String name);

    /** 内部取包（Python 引擎物化缓存用）；不存在与无权共用 404。 */
    SkillPackage packageForUser(String userId, String name);

    /** 技能包字节 + 内容 sha（缓存键）。 */
    record SkillPackage(byte[] data, String sha) {
    }
}
