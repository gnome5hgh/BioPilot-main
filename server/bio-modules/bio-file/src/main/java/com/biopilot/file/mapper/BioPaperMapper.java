package com.biopilot.file.mapper;

import com.baomidou.mybatisplus.annotation.InterceptorIgnore;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.biopilot.file.domain.BioPaper;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

/** bio_paper 的 CRUD。
 *
 * <p>面向浏览器的操作由租户插件统一注入 user_id；{@code selectForAgent} 供 Python
 * 引擎内部调用（没有登录态），显式带 user_id 并跳过租户注入——这是「取回本人附件
 * 原文」这一条路径的受控例外。</p>
 */
@Mapper
public interface BioPaperMapper extends BaseMapper<BioPaper> {

    /** 内部路径按 (user_id, id) 精确取行；不存在与无权共用 404 语义。 */
    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT * FROM bio_paper WHERE id=#{id} AND user_id=#{userId} LIMIT 1")
    BioPaper selectForAgent(@Param("userId") String userId, @Param("id") String id);
}
