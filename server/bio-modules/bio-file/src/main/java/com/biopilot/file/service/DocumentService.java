package com.biopilot.file.service;

import com.biopilot.file.dto.DocumentSummary;
import com.biopilot.file.dto.DocumentView;
import java.util.List;
import java.util.Map;

/** 文档编辑器：bio_document 元数据 + OSS 正文。 */
public interface DocumentService {

    /** 本用户的文档清单（新→旧）。 */
    List<DocumentSummary> list(long userId);

    /** 新建文档（同名检查 + 对象先落、行后写）。 */
    Map<String, Object> create(long userId, Map<String, Object> body);

    /** 读取文档全文（OSS 不可达时回退行内 content）。 */
    DocumentView get(long userId, String docId);

    /** 保存文档（改名时跳过自身做同名检查）。 */
    Map<String, Object> save(long userId, String docId, Map<String, Object> body);

    /** agent 成稿入库：按 (user_id, name) upsert。 */
    Map<String, Object> saveByName(String userId, String rawName, String content);

    /** 删除文档（行先删、对象后删）。 */
    void delete(long userId, String docId);
}
