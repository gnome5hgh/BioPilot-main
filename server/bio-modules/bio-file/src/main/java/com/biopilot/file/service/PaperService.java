package com.biopilot.file.service;

import com.biopilot.file.domain.BioPaper;
import com.biopilot.file.dto.AgentFileData;
import com.biopilot.file.dto.DownloadData;
import com.biopilot.file.dto.PaperView;
import java.util.List;
import java.util.Map;
import org.springframework.web.multipart.MultipartFile;

/** 论文目录：bio_paper 的身份/文件/书目列 + OSS 对象生命周期。 */
public interface PaperService {

    /** 上传一份 PDF（可选同时加入知识库）。 */
    PaperView create(long userId, MultipartFile file, boolean addToKb);

    /** 登记一份 PDF（上传或文献导入口径相同）。 */
    PaperView ingest(long userId, String title, String authors, String year,
                     String journal, String fileName, byte[] data,
                     String contentType, boolean addToKb);

    /** 预检论文文件名是否与本人已有文件重名。 */
    void assertNameAvailable(String fileName);

    /** 登记已落 OSS 的对象（文献导入的异步路径）。 */
    void register(long userId, String paperId, Map<String, Object> body);

    /** 本用户的论文清单（新→旧）。 */
    List<PaperView> list(long userId);

    /** 按 id 取本人论文；不存在抛 404。 */
    BioPaper get(long userId, String paperId);

    /** 事务内锁住论文行（加入引用库时防并发重复插入）。 */
    BioPaper getForUpdate(long userId, String paperId);

    /** 写入/清空论文的引用库关联列。 */
    void linkCitation(long userId, String paperId, String citationId);

    /** 按引用库行 id 清空论文的关联列（缺外键时的兜底）。 */
    void clearCitationByCitationId(String citationId);

    /** 更新论文书目字段；标题变化且在知识库时重新排队索引。 */
    void updateMetadata(long userId, String paperId, Map<String, Object> body);

    /** 下载论文原文。 */
    DownloadData download(long userId, String paperId);

    /** 内部路径取回论文原文（引擎索引用）。 */
    AgentFileData loadForAgent(String userId, String paperId);

    /** 删除论文（行 + OSS 对象 + 引用库联动）；返回对象键。 */
    String delete(long userId, String paperId);
}
