package com.biopilot.system.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.biopilot.system.domain.SysUser;
import org.apache.ibatis.annotations.Mapper;

/** sys_user 表 Mapper（MyBatis-Plus BaseMapper 提供基础 CRUD）。 */
@Mapper
public interface SysUserMapper extends BaseMapper<SysUser> {
}
