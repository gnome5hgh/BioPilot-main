package com.biopilot.file.mapper;

import com.baomidou.mybatisplus.annotation.InterceptorIgnore;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.biopilot.file.domain.BioDocument;
import java.util.List;
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

    /** 内部路径按 (user_id, id) 取行（成稿 upsert 时读旧对象键）。 */
    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT * FROM bio_document WHERE user_id=#{userId} AND id=#{id} LIMIT 1")
    BioDocument selectByIdForAgent(@Param("userId") String userId, @Param("id") String id);

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

    /** 同用户下还有多少行引用这个对象键（判断旧的名字基键是否仍被共享）。 */
    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT COUNT(*) FROM bio_document WHERE user_id=#{userId} AND oss_key=#{ossKey}")
    int countByOssKeyForUser(@Param("userId") String userId,
                             @Param("ossKey") String ossKey);

    /** 启动回填：按更新顺序读出全部文档（含正文与对象键）。 */
    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT id, user_id, name, content, oss_key, updated_at FROM bio_document"
            + " ORDER BY updated_at, seq")
    List<BioDocument> selectAllForCatalogBackfill();

    /** 回填：改名并把对象键迁到 id 基（显式按主键更新，无登录态）。 */
    @InterceptorIgnore(tenantLine = "true")
    @Update("UPDATE bio_document SET name=#{name}, oss_key=#{ossKey}, updated_at=#{updatedAt}"
            + " WHERE id=#{id}")
    int updateForCatalogBackfill(@Param("id") String id,
                                 @Param("name") String name,
                                 @Param("ossKey") String ossKey,
                                 @Param("updatedAt") String updatedAt);
}
