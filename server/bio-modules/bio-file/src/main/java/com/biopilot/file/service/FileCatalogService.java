package com.biopilot.file.service;

import com.biopilot.common.core.exception.ServiceException;
import com.biopilot.file.domain.UserFileKind;

/**
 * 用户文件同名约束：论文 / 数据文件 / 文档三类共用一个名字空间。
 *
 * <p>名字的唯一性由 {@code bio_user_file} 的唯一键裁决：创建时先占名、再写业务行，
 * 两者必须在同一事务里。分析产物不参与（可跨 run 重名）。</p>
 */
public interface FileCatalogService {

    /** 一条已占名的登记（kind + 业务主键 + 展示名）。 */
    record Reservation(String kind, String refId, String name) {
    }

    /** 浏览器预检：命中同名即抛 409（文献导入在下载前先挡掉）。 */
    void assertNameAvailable(String name);

    /** 更新场景预检：跳过当前业务对象自身（按 kind + refId），其余同名仍拒绝。 */
    void assertNameAvailable(String name, String excludeKind, String excludeRefId);

    /** 同名冲突的统一异常文案。 */
    static ServiceException conflict(String name, String kind) {
        return new ServiceException(409,
                "已存在同名文件「" + name + "」（" + UserFileKind.labelOf(kind)
                        + "），请改名后再试");
    }

    /**
     * 在当前事务里占名；撞唯一键抛 409。
     *
     * @param userId 归属用户（内部调用没有登录态，必须显式传）
     * @param kind   文件类型（{@link com.biopilot.file.domain.UserFileKind} 的 code）
     * @param name   展示名（内部会做 NFC + trim + lower 归一化）
     * @param refId  业务表主键
     */
    void reserve(String userId, String kind, String name, String refId);

    /** 按用户 + 归一化名查登记；不存在返回 null（内部路径同样可用）。 */
    Reservation find(String userId, String name);

    /**
     * 改名（浏览器路径，租户插件注入 user_id）；撞同名抛 409。
     *
     * @param userId  归属用户（用于冲突文案定位对手类型）
     * @param kind    文件类型
     * @param refId   业务表主键
     * @param newName 新展示名
     */
    void rename(String userId, String kind, String refId, String newName);

    /**
     * 释放名字；业务行删除必须在同一事务里。
     *
     * @param userId 归属用户（内部路径没有登录态，显式传）
     * @param kind   文件类型
     * @param refId  业务表主键
     */
    void release(String userId, String kind, String refId);

    /** 归一化键：NFC + trim + lower(Locale.ROOT)，也是唯一键的内容。 */
    String nameKey(String name);
}
