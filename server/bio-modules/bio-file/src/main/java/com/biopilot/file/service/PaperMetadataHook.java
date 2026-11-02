package com.biopilot.file.service;

/** 论文书目字段变更时的扩展点：引用库同步更新自己的行。

    引用库行是论文元数据的快照；标题/作者/年份/期刊改动后由引用域更新，
    避免文件管理与引用库展示不一致。
*/
public interface PaperMetadataHook {

    /** 论文书目字段变更后调用（同一事务）。
     *
     * Args:
     *     citationId: 关联的引用库行 id；未加入引用库时为空。
     *     title: 最新标题。
     *     authors: 最新作者。
     *     year: 最新年份。
     *     journal: 最新期刊。
     */
    void onPaperMetadataChanged(String citationId, String title, String authors,
                                String year, String journal);
}
