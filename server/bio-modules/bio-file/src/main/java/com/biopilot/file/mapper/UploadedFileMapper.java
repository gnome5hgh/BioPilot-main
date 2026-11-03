package com.biopilot.file.mapper;

import com.baomidou.mybatisplus.annotation.InterceptorIgnore;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.biopilot.file.domain.UploadedFile;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

/** bio_file_upload 的 CRUD。
 *
 * <p>面向浏览器的操作由租户插件统一注入 user_id；{@code selectForAgent} 供 Python
 * 引擎内部调用（没有登录态），显式带 user_id 并跳过租户注入。</p>
 */
@Mapper
public interface UploadedFileMapper extends BaseMapper<UploadedFile> {

    /** 内部路径按 (user_id, id) 精确取行；不存在与无权共用 404 语义。 */
    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT * FROM bio_file_upload WHERE id=#{id} AND user_id=#{userId} LIMIT 1")
    UploadedFile selectForAgent(@Param("userId") String userId, @Param("id") String id);

    /** 启动回填：只读用户上传的文件；分析产物可跨 run 重名，不参与同名登记。 */
    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT id, user_id, name, oss_key, source, created_at FROM bio_file_upload"
            + " WHERE source = 'upload' ORDER BY created_at, seq")
    List<UploadedFile> selectAllForCatalogBackfill();

    /** 回填时给同名落败者改名。 */
    @InterceptorIgnore(tenantLine = "true")
    @Update("UPDATE bio_file_upload SET name=#{name} WHERE id=#{id}")
    int updateNameForCatalogBackfill(@Param("id") String id, @Param("name") String name);
}
