package com.biopilot.file.service;

/** 用户文件同名约束：论文 / 数据文件 / 文档三类共用一个名字空间。 */
public interface FileCatalogService {

    /** 命中同名即抛 409；三种类型分别给用户可读文案。 */
    void assertNameAvailable(String name);

    /** 更新场景：跳过当前业务对象自身（按 kind + id），其余同名仍拒绝。 */
    void assertNameAvailable(String name, String excludeKind, String excludeId);
}
