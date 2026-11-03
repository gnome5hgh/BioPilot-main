package com.biopilot.file.mapper;

import com.baomidou.mybatisplus.annotation.InterceptorIgnore;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.biopilot.file.domain.BioPaper;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

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

    /** 启动回填：按创建顺序读出全部论文的身份/文件名/对象键。 */
    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT id, user_id, file_name, oss_key, created_at FROM bio_paper"
            + " ORDER BY created_at, seq")
    List<BioPaper> selectAllForCatalogBackfill();

    /** 回填时给同名落败者改名（没有登录态，显式按主键更新）。 */
    @InterceptorIgnore(tenantLine = "true")
    @Update("UPDATE bio_paper SET file_name=#{name} WHERE id=#{id}")
    int updateFileNameForCatalogBackfill(@Param("id") String id, @Param("name") String name);
}
