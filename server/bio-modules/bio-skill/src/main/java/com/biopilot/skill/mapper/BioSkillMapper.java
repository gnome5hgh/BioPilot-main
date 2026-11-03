package com.biopilot.skill.mapper;

import com.baomidou.mybatisplus.annotation.InterceptorIgnore;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.biopilot.skill.domain.BioSkill;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

/**
 * bio_skill 的 CRUD。
 *
 * <p>面向浏览器的操作由租户插件统一注入 user_id；{@code selectForAgent} 供 Python
 * 引擎内部取包（没有登录态），显式带 user_id 并跳过租户注入。</p>
 */
@Mapper
public interface BioSkillMapper extends BaseMapper<BioSkill> {

    /** 内部路径按 (user_id, name) 精确取行；不存在与无权共用 404 语义。 */
    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT * FROM bio_skill WHERE user_id=#{userId} AND name=#{name} LIMIT 1")
    BioSkill selectForAgent(@Param("userId") String userId, @Param("name") String name);
}
