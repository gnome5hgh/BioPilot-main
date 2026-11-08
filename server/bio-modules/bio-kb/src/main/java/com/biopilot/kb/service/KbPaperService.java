package com.biopilot.kb.service;

import com.biopilot.kb.dto.KbPaperView;
import java.util.List;

/** 知识库论文清单与勾选：{@code bio_file} 的 kb_enabled 列归本服务写。

    <p>论文身份/文件/书目列归 {@code bio-file}；本服务只读这些列、只写
    {@code kb_enabled} 与索引状态列，因此不引用 {@code bio-file} 的 mapper 或实体。</p>
*/
public interface KbPaperService {

    /**
     * 本用户的论文清单（新→旧）。
     *
     * Args:
     *     userId: 归属用户。
     *     filter: {@code all} / {@code in}（已在知识库）/ {@code out}（未加入）。
     *
     * Returns:
     *     前端知识库页与文件管理页共用的论文视图。
     */
    List<KbPaperView> list(long userId, String filter);

    /** 加入知识库并把该篇置为排队；返回实际更新的行数。 */
    int add(long userId, List<String> paperIds);

    /** 移出知识库并清空索引状态；返回实际更新的行数。 */
    int remove(long userId, List<String> paperIds);

    /** 重试失败论文（仍在知识库的行置回排队）；返回实际更新的行数。 */
    int retry(long userId, List<String> paperIds);
}
