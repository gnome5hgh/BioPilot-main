package com.biopilot.catalog.mapper;

import com.baomidou.mybatisplus.annotation.InterceptorIgnore;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.biopilot.catalog.domain.BioDocument;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

/**
 * bio_document 的 CRUD。
 *
 * <p>面向浏览器的普通操作由租户插件统一注入 user_id；下面三个 {@code *ForAgent} 方法
 * 供 Python 引擎内部调用（没有登录态），显式带 user_id 并跳过租户注入——这是
 * 「agent 成稿入库」这一条路径的受控例外，不用于任何前端请求。</p>
 */
@Mapper
public interface BioDocumentMapper extends BaseMapper<BioDocument> {

    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT * FROM bio_document WHERE user_id=#{userId} AND name=#{name} LIMIT 1")
    BioDocument selectByUserAndNameForAgent(@Param("userId") String userId,
                                            @Param("name") String name);

    @InterceptorIgnore(tenantLine = "true")
    @Insert("INSERT INTO bio_document (id, user_id, name, content, oss_key, updated_at)"
            + " VALUES (#{id}, #{userId}, #{name}, #{content}, #{ossKey}, #{updatedAt})")
    int insertForAgent(@Param("id") String id,
                       @Param("userId") String userId,
                       @Param("name") String name,
                       @Param("content") String content,
                       @Param("ossKey") String ossKey,
                       @Param("updatedAt") String updatedAt);

    @InterceptorIgnore(tenantLine = "true")
    @Update("UPDATE bio_document SET content=#{content}, oss_key=#{ossKey}, updated_at=#{updatedAt}"
            + " WHERE id=#{id} AND user_id=#{userId}")
    int updateForAgent(@Param("id") String id,
                       @Param("userId") String userId,
                       @Param("content") String content,
                       @Param("ossKey") String ossKey,
                       @Param("updatedAt") String updatedAt);
}
