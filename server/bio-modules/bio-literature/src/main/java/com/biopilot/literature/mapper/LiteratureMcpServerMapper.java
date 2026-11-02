package com.biopilot.literature.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.biopilot.literature.domain.LiteratureMcpServer;
import org.apache.ibatis.annotations.Mapper;

/** bio_literature_mcp_server 的 CRUD（全局配置，不参与租户过滤）。 */
@Mapper
public interface LiteratureMcpServerMapper extends BaseMapper<LiteratureMcpServer> {
}
