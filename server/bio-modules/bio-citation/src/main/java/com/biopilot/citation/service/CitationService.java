package com.biopilot.citation.service;

import com.biopilot.citation.dto.CitationView;
import java.util.List;
import java.util.Map;

/** 平台引用库：加入/移出、库外条目维护、按样式渲染与导出。 */
public interface CitationService {

    /** 列表/搜索：按标题、作者、key 的子串匹配（空查询返回全部）。 */
    List<CitationView> list(String q);

    /** 按样式渲染指定 key（未知 key 静默跳过）。 */
    String format(List<String> keys, String style);

    /** 导出当前用户全部条目为 .bib 文本。 */
    String export();

    /** 从文件管理里的论文加入引用库（幂等）。 */
    CitationView fromPaper(long userId, String paperId);

    /** 按论文移出引用库。 */
    boolean removeByPaper(long userId, String paperId);

    /** 按 key 删除库外条目。 */
    boolean remove(String key);

    /** 新增库外条目。 */
    CitationView addExternal(long userId, Map<String, Object> body);

    /** 更新库外条目。 */
    CitationView updateExternal(String key, Map<String, Object> body);
}
