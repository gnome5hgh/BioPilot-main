package com.biopilot.system.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.biopilot.system.domain.LoginLog;
import org.apache.ibatis.annotations.Mapper;

/** sys_login_log 表 Mapper。 */
@Mapper
public interface LoginLogMapper extends BaseMapper<LoginLog> {
}
