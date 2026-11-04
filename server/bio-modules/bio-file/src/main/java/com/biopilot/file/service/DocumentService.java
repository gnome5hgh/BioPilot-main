package com.biopilot.file.service;

import com.biopilot.file.dto.DocumentSummary;
import com.biopilot.file.dto.DocumentView;
import java.util.List;
import java.util.Map;

/** 文档编辑器：bio_file 的 document 行 + OSS 正文。 */
public interface DocumentService {

    /** 本用户的文档清单（新→旧）。 */
    List<DocumentSummary> list(long userId);

    /** 新建文档（同名检查 + 对象先落、行后写）。 */
    Map<String, Object> create(long userId, Map<String, Object> body);

    /** 读取文档全文（OSS 不可达时返回 502，不返回空文档）。 */
    DocumentView get(long userId, String docId);

    /** 内部路径按 id 读取（X-User-Id 可能是 local 等非数字域）。 */
    DocumentView getForAgent(String userId, String docId);

    /** 内部路径按归一化名读取。 */
    DocumentView getByName(String userId, String rawName);

    /** 内部路径的文档清单。 */
    List<DocumentSummary> listForAgent(String userId);

    /** 保存文档（版本条件更新）。 */
    Map<String, Object> save(long userId, String docId, Map<String, Object> body);

    /** agent 成稿入库：按 (user_id, name) upsert；expectedVersion 非空时做乐观锁。 */
    Map<String, Object> saveByName(String userId, String rawName, String content,
                                   Long expectedVersion);

    /** 删除文档（行先删、对象交给 GC）。 */
    void delete(long userId, String docId);

    /** 内部路径删除文档。 */
    void deleteForAgent(String userId, String docId);
}
