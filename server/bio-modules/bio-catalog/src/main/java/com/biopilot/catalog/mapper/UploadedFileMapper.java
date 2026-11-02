package com.biopilot.catalog.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.biopilot.catalog.domain.UploadedFile;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface UploadedFileMapper extends BaseMapper<UploadedFile> {
}
