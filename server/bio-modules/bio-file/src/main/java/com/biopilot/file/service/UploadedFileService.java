package com.biopilot.file.service;

import com.biopilot.file.dto.AgentFileData;
import com.biopilot.file.dto.DownloadData;
import com.biopilot.file.dto.FileListItem;
import com.biopilot.file.dto.FileView;
import java.util.List;
import org.springframework.web.multipart.MultipartFile;

/** 数据文件（对话附件/分析产物）：bio_file 的 data/artifact 行 + OSS 对象。 */
public interface UploadedFileService {

    /** 用户上传：同名检查 + 先落对象、后写行。 */
    FileView upload(long userId, MultipartFile file);

    /** 本用户的数据文件清单（新→旧，最多 100 条）。 */
    List<FileListItem> list(long userId);

    /** 内部路径列出本用户的 data/artifact。 */
    List<FileListItem> listForAgent(String userId, int limit);

    /** 内部路径按 run 列出产物。 */
    List<FileListItem> listByRun(String userId, String runId, int limit);

    /** 下载数据文件。 */
    DownloadData download(long userId, String fileId);

    /** 内部路径取回数据文件（引擎读字节用）。 */
    AgentFileData loadForAgent(String userId, String fileId);

    /** agent 分析产物入库：不做同名检查（跨 run 重名正常）。 */
    FileView uploadArtifact(String userId, String runId, MultipartFile file);

    /** 删除数据文件（行先删、对象交给 GC）。 */
    void delete(long userId, String fileId);

    /** 内部路径删除数据文件。 */
    void deleteForAgent(String userId, String fileId);
}
