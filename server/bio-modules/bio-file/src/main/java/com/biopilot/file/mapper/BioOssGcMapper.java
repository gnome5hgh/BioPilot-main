package com.biopilot.file.mapper;

import com.baomidou.mybatisplus.annotation.InterceptorIgnore;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.biopilot.file.domain.BioOssGc;
import java.util.List;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

/** {@code bio_oss_gc} 的 CRUD 与到期扫描。 */
@Mapper
public interface BioOssGcMapper extends BaseMapper<BioOssGc> {

    /** 同一个对象重复入队只保留一行。 */
    @InterceptorIgnore(tenantLine = "true")
    @Insert("INSERT IGNORE INTO bio_oss_gc (oss_key, reason, attempts, next_at, created_at)"
            + " VALUES (#{ossKey}, #{reason}, 0, #{nextAt}, #{createdAt})")
    int insertIgnore(@Param("ossKey") String ossKey,
                     @Param("reason") String reason,
                     @Param("nextAt") String nextAt,
                     @Param("createdAt") String createdAt);

    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT * FROM bio_oss_gc WHERE next_at IS NULL OR next_at <= #{now}"
            + " ORDER BY id LIMIT #{limit}")
    List<BioOssGc> selectDue(@Param("now") String now, @Param("limit") int limit);
}
