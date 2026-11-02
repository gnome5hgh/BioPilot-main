package com.biopilot.project.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.biopilot.project.domain.BioProject;
import org.apache.ibatis.annotations.Mapper;

/** bio_project 表 Mapper。 */
@Mapper
public interface BioProjectMapper extends BaseMapper<BioProject> {
}
