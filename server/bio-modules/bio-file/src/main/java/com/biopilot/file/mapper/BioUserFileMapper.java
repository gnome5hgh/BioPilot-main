package com.biopilot.file.mapper;

import com.baomidou.mybatisplus.annotation.InterceptorIgnore;
import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.biopilot.file.domain.BioUserFile;
import java.util.List;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

/**
 * bio_user_file 的 CRUD。
 *
 * <p>占名与按名字查冲突同时服务浏览器与引擎内部调用（成稿入库、文献登记、启动回填），
 * 内部路径没有登录态，故这些方法显式带 {@code user_id} 并跳过租户注入——与各业务
 * Mapper 的 {@code *ForAgent} 同一受控例外。改名/释放只走浏览器路径，用
 * {@link BaseMapper} 的 Wrapper 由租户插件注入。</p>
 */
@Mapper
public interface BioUserFileMapper extends BaseMapper<BioUserFile> {

    /**
     * 原子占名：命中唯一键时退化为 no-op，不抛异常。
     *
     * <p>返回值不要用来判断「是否新占」——JDBC 驱动默认 CLIENT_FOUND_ROWS，
     * 命中已有行时 affected rows 也可能是 1。调用方以插入后按名字读回的 ref 为准。</p>
     *
     * @param row 待登记行（id 由数据库自增）
     * @return 驱动报告的受影响行数（仅作连接层观测，不承载业务语义）
     */
    @InterceptorIgnore(tenantLine = "true")
    @Insert("INSERT INTO bio_user_file (user_id, kind, name_key, name, ref_id, created_at)"
            + " VALUES (#{userId}, #{kind}, #{nameKey}, #{name}, #{refId}, #{createdAt})"
            + " ON DUPLICATE KEY UPDATE id = id")
    int tryReserve(BioUserFile row);

    /** 回填专用：撞唯一键就跳过，不覆盖已占名。 */
    @InterceptorIgnore(tenantLine = "true")
    @Insert("INSERT IGNORE INTO bio_user_file (user_id, kind, name_key, name, ref_id, created_at)"
            + " VALUES (#{userId}, #{kind}, #{nameKey}, #{name}, #{refId}, #{createdAt})")
    int insertIgnore(BioUserFile row);

    /** 按 (user_id, 归一化名) 取登记行；不存在返回 null。 */
    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT * FROM bio_user_file WHERE user_id=#{userId} AND name_key=#{nameKey}"
            + " LIMIT 1")
    BioUserFile selectByNameKeyForUser(@Param("userId") String userId,
                                       @Param("nameKey") String nameKey);

    /** 释放名字；显式 user_id（删除与 agent 成稿更新都可能没有登录态）。 */
    @InterceptorIgnore(tenantLine = "true")
    @Delete("DELETE FROM bio_user_file WHERE user_id=#{userId} AND kind=#{kind}"
            + " AND ref_id=#{refId}")
    int deleteByUserAndRef(@Param("userId") String userId,
                           @Param("kind") String kind,
                           @Param("refId") String refId);

    /** 启动回填：全量读出已登记对象（量级=用户文件数，实验室规模可接受）。 */
    @InterceptorIgnore(tenantLine = "true")
    @Select("SELECT id, user_id, kind, name_key, name, ref_id, created_at FROM bio_user_file")
    List<BioUserFile> selectAllForBackfill();
}
