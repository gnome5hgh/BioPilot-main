package com.biopilot.literature.dto;

import java.util.List;

/**
 * 管理端展示的 MCP server 配置视图。
 *
 * <p>env / headers 的具体值不回显，只告诉前端「是否已配置」，避免密钥经接口或日志
 * 泄漏；编辑时前端不回填这两项，留空表示保持原值。</p>
 *
 * @param id                主键
 * @param name              名称
 * @param transport         stdio / http
 * @param url               http 端点
 * @param command           stdio 可执行文件
 * @param args              stdio 参数
 * @param envConfigured     是否已配置 env 密钥
 * @param headersConfigured 是否已配置请求头
 * @param adapter           业务适配器（paper_search）
 * @param allowedTools      工具白名单
 * @param disabledTools     工具黑名单
 * @param enabled           是否启用
 * @param connectTimeoutMs  建连超时
 * @param callTimeoutMs     调用超时
 */
public record LiteratureMcpServerView(
        String id,
        String name,
        String transport,
        String url,
        String command,
        List<String> args,
        boolean envConfigured,
        boolean headersConfigured,
        String adapter,
        List<String> allowedTools,
        List<String> disabledTools,
        boolean enabled,
        int connectTimeoutMs,
        int callTimeoutMs) {
}
