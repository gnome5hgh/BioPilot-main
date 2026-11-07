package com.biopilot.file.mapper;

import com.baomidou.mybatisplus.annotation.InterceptorIgnore;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.biopilot.file.domain.BioFile;
import com.biopilot.file.domain.PaperIndexStatus;
import java.util.List;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

/**
 * {@code bio_file} 的 CRUD。
 *
 * <p>面向浏览器的普通操作由租户插件注入 user_id；带 {@code ForAgent} 后缀的方法
 * 供 Python 引擎内部调用（没有登录态），显式带 user_id 且跳过租户注入。所有写
 * 路径都对 {@code kind} 做约束，避免同一张表跨类型误改。</p>
 */
@Mapper
public interface BioFileMapper extends BaseMapper<BioFile> {

    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT * FROM bio_file WHERE user_id=#{userId} AND kind=#{kind}"
            + " AND id=#{id} LIMIT 1")
    BioFile selectForAgent(@Param("userId") String userId,
                           @Param("kind") String kind,
                           @Param("id") String id);

    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT * FROM bio_file WHERE user_id=#{userId} AND kind=#{kind}"
            + " AND name_key=#{nameKey} LIMIT 1")
    BioFile selectByNameForAgent(@Param("userId") String userId,
                                 @Param("kind") String kind,
                                 @Param("nameKey") String nameKey);

    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT * FROM bio_file WHERE user_id=#{userId} AND name_key=#{nameKey}"
            + " LIMIT 1")
    BioFile selectAnyByNameForAgent(@Param("userId") String userId,
                                    @Param("nameKey") String nameKey);

    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT * FROM bio_file WHERE user_id=#{userId} AND id=#{id}"
            + " AND kind IN ('data','artifact') LIMIT 1")
    BioFile selectDataForAgent(@Param("userId") String userId,
                               @Param("id") String id);

    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT * FROM bio_file WHERE user_id=#{userId} AND kind='paper'"
            + " AND id=#{id} FOR UPDATE")
    BioFile selectPaperForUpdate(@Param("userId") String userId,
                                 @Param("id") String id);

    /**
     * 条件更新文档指针：只有版本仍等于读取时的值才写入。
     *
     * <p>0 行表示另一写者已经先提交，调用方必须返回 409；新对象作为孤儿交给 GC。</p>
     */
    @InterceptorIgnore(tenantLine = "true")
    @Update("UPDATE bio_file SET oss_key=#{ossKey}, sha256=#{sha256},"
            + " size_bytes=#{sizeBytes}, content_type=#{contentType},"
            + " version=#{version}, name=#{name}, name_key=#{nameKey},"
            + " updated_at=#{updatedAt}"
            + " WHERE id=#{id} AND user_id=#{userId} AND kind='document'"
            + " AND version=#{expectedVersion}")
    int updateDocumentForAgent(@Param("id") String id,
                               @Param("userId") String userId,
                               @Param("name") String name,
                               @Param("nameKey") String nameKey,
                               @Param("ossKey") String ossKey,
                               @Param("sha256") String sha256,
                               @Param("sizeBytes") long sizeBytes,
                               @Param("contentType") String contentType,
                               @Param("version") long version,
                               @Param("updatedAt") String updatedAt,
                               @Param("expectedVersion") long expectedVersion);

    @InterceptorIgnore(tenantLine = "true")
    @Update("UPDATE bio_file SET title=#{title}, authors=#{authors}, year=#{year},"
            + " journal=#{journal}, updated_at=#{updatedAt}"
            + " WHERE id=#{id} AND user_id=#{userId} AND kind='paper'")
    int updatePaperMetadataForAgent(@Param("id") String id,
                                    @Param("userId") String userId,
                                    @Param("title") String title,
                                    @Param("authors") String authors,
                                    @Param("year") String year,
                                    @Param("journal") String journal,
                                    @Param("updatedAt") String updatedAt);

    @InterceptorIgnore(tenantLine = "true")
    @Update("UPDATE bio_file SET citation_id=#{citationId}"
            + " WHERE id=#{id} AND user_id=#{userId} AND kind='paper'")
    int updateCitationForAgent(@Param("id") String id,
                               @Param("userId") String userId,
                               @Param("citationId") String citationId);

    @InterceptorIgnore(tenantLine = "true")
    @Update("UPDATE bio_file SET citation_id=NULL WHERE citation_id=#{citationId}")
    int clearCitationByCitationId(@Param("citationId") String citationId);

    @InterceptorIgnore(tenantLine = "true")
    @Delete("DELETE FROM bio_file WHERE id=#{id} AND user_id=#{userId} AND kind=#{kind}")
    int deleteForAgent(@Param("id") String id,
                       @Param("userId") String userId,
                       @Param("kind") String kind);

    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT * FROM bio_file WHERE user_id=#{userId} AND kind=#{kind}"
            + " ORDER BY seq DESC LIMIT #{limit}")
    List<BioFile> listForAgent(@Param("userId") String userId,
                               @Param("kind") String kind,
                               @Param("limit") int limit);

    /** 引擎索引状态表的跨栈只读（唯一落点与写者在引擎；展示用）。 */
    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT paper_id, indexed, index_status, index_error, indexed_at,"
            + " chunk_count FROM bio_rag_paper_status WHERE user_id=#{userId}")
    List<PaperIndexStatus> listPaperStatusForAgent(@Param("userId") String userId);

    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT * FROM bio_file WHERE user_id=#{userId}"
            + " AND kind IN ('data','artifact') ORDER BY seq DESC LIMIT #{limit}")
    List<BioFile> listDataForAgent(@Param("userId") String userId,
                                   @Param("limit") int limit);

    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT * FROM bio_file WHERE user_id=#{userId} AND run_id=#{runId}"
            + " ORDER BY seq DESC LIMIT #{limit}")
    List<BioFile> listByRunForAgent(@Param("userId") String userId,
                                    @Param("runId") String runId,
                                    @Param("limit") int limit);

    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT oss_key FROM bio_file WHERE user_id=#{userId}")
    List<String> selectOssKeysForUser(@Param("userId") String userId);

    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT DISTINCT user_id FROM bio_file")
    List<String> selectDistinctUsers();

    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT COUNT(*) FROM bio_file WHERE oss_key=#{ossKey}")
    int countByOssKey(@Param("ossKey") String ossKey);
}
