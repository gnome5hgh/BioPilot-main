package com.biopilot.citation.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.biopilot.citation.domain.BioCitation;
import org.apache.ibatis.annotations.Mapper;

/** bio_citation 的 CRUD（行级隔离由租户插件注入）。 */
@Mapper
public interface BioCitationMapper extends BaseMapper<BioCitation> {
}
